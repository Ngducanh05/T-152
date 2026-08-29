import { StrictMode } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ParkSmartApiClient } from "@/lib/api";
import type { ParkingSnapshot, UserParkingState } from "@/lib/types";
import {
  activeReservation,
  activeSession,
  canonicalMap,
  currentLocation,
  parkingStatus,
  successResponse,
} from "@/test/fixtures";

import { PARKING_POLL_INTERVAL_MS, useParkSmartData } from "./use-parksmart-data";

const rewardConfiguration = {
  adjacent_observation_reward_points: 10,
  wrong_parking_report_reward_points: 20,
  contribution_daily_points_limit: 100,
};
const rewardSummary = {
  available_points: 20,
  pending_points: 10,
  verified_contributions: 1,
  daily_pending_points: 10,
  daily_earned_points: 20,
  daily_limit_points: 100,
};
const parkingSnapshot: ParkingSnapshot = {
  slots: canonicalMap.slots,
  status: parkingStatus,
  state_version: 8,
};
const userState: UserParkingState = {
  current_location: currentLocation,
  active_reservation: activeReservation,
  active_session: activeSession,
  reward_summary: rewardSummary,
  reward_configuration: rewardConfiguration,
};

function responseFor(url: string) {
  if (url.endsWith("/parking/map")) return successResponse(canonicalMap);
  if (url.endsWith("/parking/snapshot")) return successResponse(parkingSnapshot);
  if (url.includes("/parking/users/") && url.endsWith("/state")) {
    return successResponse(userState);
  }
  if (url.includes("/contributions/users/")) return successResponse([]);
  if (url.endsWith("/rewards/configuration")) {
    return successResponse(rewardConfiguration);
  }
  if (url.endsWith("/rewards/catalog")) return successResponse([]);
  if (url.includes("/rewards/users/") && url.endsWith("/vouchers")) {
    return successResponse([]);
  }
  throw new Error(`Unexpected request: ${url}`);
}

beforeEach(() => vi.useFakeTimers());

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("loads static map, dynamic snapshot, and aggregate user state", async () => {
  let resolveMap!: (response: Response) => void;
  let resolveSnapshot!: (response: Response) => void;
  const mapRequest = new Promise<Response>((resolve) => { resolveMap = resolve; });
  const snapshotRequest = new Promise<Response>((resolve) => { resolveSnapshot = resolve; });
  const fetcher = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url.endsWith("/parking/map")) return mapRequest;
    if (url.endsWith("/parking/snapshot")) return snapshotRequest;
    return responseFor(url);
  });
  const api = new ParkSmartApiClient({ baseUrl: "http://api.test/api/v1", fetcher });
  const { result } = renderHook(() => useParkSmartData(api, "USER-001"));

  expect(result.current.loading).toBe(true);
  await act(async () => {
    resolveMap(successResponse(canonicalMap));
    resolveSnapshot(successResponse(parkingSnapshot));
    for (let index = 0; index < 8; index += 1) await Promise.resolve();
  });

  expect(result.current.loading).toBe(false);
  expect(result.current.map?.slots).toHaveLength(40);
  expect(result.current.status).toEqual(parkingStatus);
  expect(result.current.activeReservation).toEqual(activeReservation);
  expect(result.current.activeSession).toEqual(activeSession);
  expect(result.current.rewardSummary).toEqual(rewardSummary);
  expect(fetcher).toHaveBeenCalledTimes(6);
});

it("finishes aggregate loading when Strict Mode remounts the effect", async () => {
  const fetcher = vi.fn<typeof fetch>(async (input) => responseFor(String(input)));
  const api = new ParkSmartApiClient({ baseUrl: "http://api.test/api/v1", fetcher });
  const { result } = renderHook(() => useParkSmartData(api, "USER-001"), {
    wrapper: StrictMode,
  });
  await act(async () => {
    for (let index = 0; index < 16; index += 1) await Promise.resolve();
  });
  expect(result.current.loading).toBe(false);
  expect(result.current.map?.slots).toHaveLength(40);
  expect(result.current.error).toBeNull();
});

it("polls only the parking snapshot and leaves rewards for explicit refreshes", async () => {
  let snapshotCalls = 0;
  let userStateCalls = 0;
  const fetcher = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url.endsWith("/parking/snapshot")) {
      snapshotCalls += 1;
      return successResponse({ ...parkingSnapshot, state_version: 8 + snapshotCalls });
    }
    if (url.includes("/parking/users/") && url.endsWith("/state")) {
      userStateCalls += 1;
      return successResponse(userState);
    }
    return responseFor(url);
  });
  const api = new ParkSmartApiClient({ baseUrl: "http://api.test/api/v1", fetcher });
  const { result } = renderHook(() => useParkSmartData(api, "USER-001"));
  await act(async () => {
    for (let index = 0; index < 10; index += 1) await Promise.resolve();
  });
  expect(result.current.rewardSummary?.pending_points).toBe(10);

  await act(async () => {
    vi.advanceTimersByTime(PARKING_POLL_INTERVAL_MS);
    for (let index = 0; index < 5; index += 1) await Promise.resolve();
  });
  expect(snapshotCalls).toBe(2);
  expect(userStateCalls).toBe(1);
  expect(result.current.rewardSummary?.pending_points).toBe(10);
});

it("prevents overlapping snapshot polls and aborts in-flight work on unmount", async () => {
  const signals: AbortSignal[] = [];
  let snapshotCalls = 0;
  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
    if (init?.signal) signals.push(init.signal);
    const url = String(input);
    if (url.endsWith("/parking/snapshot")) {
      snapshotCalls += 1;
      if (snapshotCalls > 1) return new Promise<Response>(() => undefined);
    }
    return responseFor(url);
  });
  const api = new ParkSmartApiClient({ baseUrl: "http://api.test/api/v1", fetcher });
  const { unmount } = renderHook(() => useParkSmartData(api, "USER-001"));
  await act(async () => {
    for (let index = 0; index < 10; index += 1) await Promise.resolve();
  });
  await act(async () => {
    vi.advanceTimersByTime(PARKING_POLL_INTERVAL_MS * 3);
    await Promise.resolve();
  });
  expect(snapshotCalls).toBe(2);
  unmount();
  expect(signals.every((signal) => signal.aborted)).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
});

it("does not request user-scoped resources without a user id", async () => {
  const fetcher = vi.fn<typeof fetch>(async (input) => responseFor(String(input)));
  const api = new ParkSmartApiClient({ baseUrl: "http://api.test/api/v1", fetcher });
  const { result } = renderHook(() => useParkSmartData(api));
  await act(async () => {
    for (let index = 0; index < 10; index += 1) await Promise.resolve();
  });
  expect(result.current.loading).toBe(false);
  expect(result.current.currentLocation).toBeNull();
  expect(fetcher.mock.calls.some(([input]) => String(input).includes("/parking/users/"))).toBe(false);
  expect(fetcher.mock.calls.some(([input]) => String(input).endsWith("/rewards/configuration"))).toBe(true);
});

it("aborts the old aggregate user lifecycle when the user id changes", async () => {
  const stateSignals = new Map<string, AbortSignal[]>();
  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    const match = url.match(/\/parking\/users\/([^/]+)\/state$/);
    if (match && init?.signal) {
      const userId = decodeURIComponent(match[1]);
      stateSignals.set(userId, [...(stateSignals.get(userId) ?? []), init.signal]);
    }
    return responseFor(url);
  });
  const api = new ParkSmartApiClient({ baseUrl: "http://api.test/api/v1", fetcher });
  const { rerender } = renderHook(({ userId }) => useParkSmartData(api, userId), {
    initialProps: { userId: "USER-A" },
  });
  await act(async () => {
    for (let index = 0; index < 8; index += 1) await Promise.resolve();
  });
  rerender({ userId: "USER-B" });
  await act(async () => {
    for (let index = 0; index < 8; index += 1) await Promise.resolve();
  });
  expect(stateSignals.get("USER-A")?.every((signal) => signal.aborted)).toBe(true);
  expect(stateSignals.has("USER-B")).toBe(true);
});
