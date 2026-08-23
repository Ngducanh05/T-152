import { StrictMode } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ParkSmartApiClient } from "@/lib/api";
import {
  activeReservation,
  activeSession,
  canonicalMap,
  currentLocation,
  errorResponse,
  parkingStatus,
  successResponse,
} from "@/test/fixtures";

import { PARKING_POLL_INTERVAL_MS, useParkSmartData } from "./use-parksmart-data";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("shows initial loading until the canonical map and status arrive", async () => {
  let resolveMap!: (response: Response) => void;
  let resolveStatus!: (response: Response) => void;
  const mapRequest = new Promise<Response>((resolve) => {
    resolveMap = resolve;
  });
  const statusRequest = new Promise<Response>((resolve) => {
    resolveStatus = resolve;
  });
  const fetcher = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url.endsWith("/parking/map")) return mapRequest;
    if (url.endsWith("/parking/status")) return statusRequest;
    if (url.includes("/parking/slots")) return successResponse(canonicalMap.slots);
    if (url.includes("/locations/current")) return successResponse(currentLocation);
    if (url.includes("/reservations/active")) return successResponse(activeReservation);
    if (url.includes("/sessions/active")) return successResponse(activeSession);
    if (url.includes("/rewards/users/")) return successResponse({
      available_points: 20,
      pending_points: 10,
      verified_contributions: 1,
      daily_pending_points: 10,
      daily_earned_points: 20,
      daily_limit_points: 100,
    });
    if (url.endsWith("/rewards/configuration")) return successResponse({
      adjacent_observation_reward_points: 10,
      wrong_parking_report_reward_points: 20,
      contribution_daily_points_limit: 100,
    });
    if (url.includes("/contributions/users/")) return successResponse([]);
    throw new Error(`Unexpected request: ${url}`);
  });
  const api = new ParkSmartApiClient({
    baseUrl: "http://api.test/api/v1",
    fetcher,
  });
  const { result } = renderHook(() => useParkSmartData(api));

  expect(result.current.loading).toBe(true);
  expect(result.current.map).toBeNull();

  await act(async () => {
    resolveMap(successResponse(canonicalMap));
    resolveStatus(successResponse(parkingStatus));
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(result.current.loading).toBe(false);
  expect(result.current.map?.slots).toHaveLength(40);
  expect(result.current.status).toEqual(parkingStatus);
  expect(result.current.activeReservation).toEqual(activeReservation);
  expect(result.current.activeSession).toEqual(activeSession);
});

it("finishes initial loading when React Strict Mode remounts the effect", async () => {
  const fetcher = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url.endsWith("/parking/map")) return successResponse(canonicalMap);
    if (url.endsWith("/parking/status")) return successResponse(parkingStatus);
    if (url.includes("/parking/slots")) return successResponse(canonicalMap.slots);
    if (url.includes("/locations/current")) return successResponse(currentLocation);
    if (url.includes("/reservations/active")) {
      return errorResponse("NOT_FOUND", "Not found.", 404);
    }
    if (url.includes("/sessions/active")) {
      return errorResponse("NOT_FOUND", "Not found.", 404);
    }
    if (url.includes("/rewards/users/")) return successResponse({
      available_points: 0,
      pending_points: 0,
      verified_contributions: 0,
      daily_pending_points: 0,
      daily_earned_points: 0,
      daily_limit_points: 100,
    });
    if (url.endsWith("/rewards/configuration")) return successResponse({
      adjacent_observation_reward_points: 10,
      wrong_parking_report_reward_points: 20,
      contribution_daily_points_limit: 100,
    });
    if (url.includes("/contributions/users/")) return successResponse([]);
    throw new Error(`Unexpected request: ${url}`);
  });
  const api = new ParkSmartApiClient({
    baseUrl: "http://api.test/api/v1",
    fetcher,
  });
  const { result } = renderHook(() => useParkSmartData(api), {
    wrapper: StrictMode,
  });

  await act(async () => {
    for (let index = 0; index < 10; index += 1) {
      await Promise.resolve();
    }
  });

  expect(result.current.loading).toBe(false);
  expect(result.current.map?.slots).toHaveLength(40);
  expect(result.current.error).toBeNull();
});

it("polls the authoritative reward ledger so verified points appear without a reload", async () => {
  let rewardCalls = 0;
  const fetcher = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url.endsWith("/parking/map")) return successResponse(canonicalMap);
    if (url.endsWith("/parking/status")) return successResponse(parkingStatus);
    if (url.includes("/parking/slots")) return successResponse(canonicalMap.slots);
    if (url.includes("/locations/current") || url.includes("/reservations/active") || url.includes("/sessions/active")) {
      return errorResponse("NOT_FOUND", "Not found.", 404);
    }
    if (url.includes("/rewards/users/")) {
      rewardCalls += 1;
      return successResponse({
        available_points: rewardCalls > 1 ? 10 : 0,
        pending_points: rewardCalls > 1 ? 0 : 10,
        verified_contributions: rewardCalls > 1 ? 1 : 0,
        daily_pending_points: rewardCalls > 1 ? 0 : 10,
        daily_earned_points: rewardCalls > 1 ? 10 : 0,
        daily_limit_points: 100,
      });
    }
    if (url.endsWith("/rewards/configuration")) return successResponse({
      adjacent_observation_reward_points: 10,
      wrong_parking_report_reward_points: 20,
      contribution_daily_points_limit: 100,
    });
    if (url.includes("/contributions/users/")) return successResponse([]);
    throw new Error(`Unexpected request: ${url}`);
  });
  const api = new ParkSmartApiClient({ baseUrl: "http://api.test/api/v1", fetcher });
  const { result } = renderHook(() => useParkSmartData(api));

  await act(async () => {
    for (let index = 0; index < 8; index += 1) await Promise.resolve();
  });
  expect(result.current.rewardSummary?.pending_points).toBe(10);

  await act(async () => {
    vi.advanceTimersByTime(PARKING_POLL_INTERVAL_MS);
    for (let index = 0; index < 8; index += 1) await Promise.resolve();
  });
  expect(result.current.rewardSummary?.available_points).toBe(10);
  expect(result.current.rewardSummary?.pending_points).toBe(0);
});

it("prevents overlapping polls and aborts requests and timers on unmount", async () => {
  const signals: AbortSignal[] = [];
  let statusCalls = 0;
  let slotCalls = 0;
  const neverResolve = () => new Promise<Response>(() => undefined);

  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
    if (init?.signal) signals.push(init.signal);
    const url = String(input);
    if (url.endsWith("/parking/map")) {
      return successResponse(canonicalMap);
    }
    if (url.endsWith("/parking/status")) {
      statusCalls += 1;
      return statusCalls === 1
        ? successResponse(parkingStatus)
        : neverResolve();
    }
    if (url.includes("/parking/slots")) {
      slotCalls += 1;
      return slotCalls === 1 ? successResponse(canonicalMap.slots) : neverResolve();
    }
    if (url.includes("/rewards/users/")) return successResponse({
      available_points: 0,
      pending_points: 0,
      verified_contributions: 0,
      daily_pending_points: 0,
      daily_earned_points: 0,
      daily_limit_points: 100,
    });
    if (url.endsWith("/rewards/configuration")) return successResponse({
      adjacent_observation_reward_points: 10,
      wrong_parking_report_reward_points: 20,
      contribution_daily_points_limit: 100,
    });
    if (url.includes("/contributions/users/")) return successResponse([]);
    return errorResponse("NOT_FOUND", "Not found.", 404, "req-404");
  });
  const api = new ParkSmartApiClient({
    baseUrl: "http://api.test/api/v1",
    fetcher,
  });

  const { result, unmount } = renderHook(() => useParkSmartData(api));
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(result.current.loading).toBe(false);
  expect(result.current.currentLocation).toBeNull();
  expect(result.current.activeReservation).toBeNull();
  expect(result.current.activeSession).toBeNull();

  await act(async () => {
    vi.advanceTimersByTime(PARKING_POLL_INTERVAL_MS);
    await Promise.resolve();
  });
  expect(slotCalls).toBe(2);

  await act(async () => {
    vi.advanceTimersByTime(PARKING_POLL_INTERVAL_MS * 3);
    await Promise.resolve();
  });
  expect(slotCalls).toBe(2);

  unmount();
  expect(signals.every((signal) => signal.aborted)).toBe(true);
  expect(vi.getTimerCount()).toBe(0);

  vi.advanceTimersByTime(PARKING_POLL_INTERVAL_MS * 2);
  expect(slotCalls).toBe(2);
});
