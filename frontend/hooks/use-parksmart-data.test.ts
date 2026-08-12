import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ParkSmartApiClient } from "@/lib/api";

import { PARKING_POLL_INTERVAL_MS, useParkSmartData } from "./use-parksmart-data";

function success(data: unknown) {
  return new Response(
    JSON.stringify({ success: true, data, message: null }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

function optional404() {
  return new Response(
    JSON.stringify({
      success: false,
      error: { code: "NOT_FOUND", message: "Not found.", request_id: "req-404" },
    }),
    { status: 404, headers: { "Content-Type": "application/json" } },
  );
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it("prevents overlapping polls and aborts requests and timers on unmount", async () => {
  const signals: AbortSignal[] = [];
  let statusCalls = 0;
  let slotCalls = 0;
  const neverResolve = () => new Promise<Response>(() => undefined);

  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
    if (init?.signal) signals.push(init.signal);
    const url = String(input);
    if (url.endsWith("/parking/map")) {
      return success({ nodes: [], edges: [], slots: [] });
    }
    if (url.endsWith("/parking/status")) {
      statusCalls += 1;
      return statusCalls === 1
        ? success({
            total: 40,
            available: 40,
            reserved: 0,
            occupied: 0,
            by_zone: {},
          })
        : neverResolve();
    }
    if (url.includes("/parking/slots")) {
      slotCalls += 1;
      return neverResolve();
    }
    return optional404();
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
  expect(slotCalls).toBe(1);

  await act(async () => {
    vi.advanceTimersByTime(PARKING_POLL_INTERVAL_MS * 3);
    await Promise.resolve();
  });
  expect(slotCalls).toBe(1);

  unmount();
  expect(signals.every((signal) => signal.aborted)).toBe(true);
  expect(vi.getTimerCount()).toBe(0);

  vi.advanceTimersByTime(PARKING_POLL_INTERVAL_MS * 2);
  expect(slotCalls).toBe(1);
});
