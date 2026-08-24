import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { parkSmartApi } from "@/lib/api";
import {
  ATTEMPT_TIMEOUT_MS,
  BackendReadinessGate,
  READINESS_DEADLINE_MS,
  RETRY_DELAY_MS,
  WAKE_NOTICE_DELAY_MS,
} from "./BackendReadinessGate";

vi.mock("@/lib/api", () => ({
  parkSmartApi: {
    checkDatabaseHealth: vi.fn(),
  },
}));

const checkDatabaseHealth = vi.mocked(parkSmartApi.checkDatabaseHealth);

async function flushPromises() {
  await act(async () => {
    await Promise.resolve();
  });
}

function abortablePending(signal?: AbortSignal) {
  return new Promise<never>((_resolve, reject) => {
    signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  checkDatabaseHealth.mockReset();
});

afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("BackendReadinessGate", () => {
  it("renders children immediately after database readiness succeeds", async () => {
    const childMount = vi.fn();
    checkDatabaseHealth.mockResolvedValue({ database: "connected" });

    function ChildProbe() {
      childMount();
      return <div>Ứng dụng đã sẵn sàng</div>;
    }

    render(
      <BackendReadinessGate>
        <ChildProbe />
      </BackendReadinessGate>,
    );
    await flushPromises();

    expect(screen.getByText("Ứng dụng đã sẵn sàng")).toBeVisible();
    expect(screen.queryByText(/khởi động máy chủ miễn phí/i)).not.toBeInTheDocument();
    expect(childMount).toHaveBeenCalledTimes(1);
    expect(checkDatabaseHealth).toHaveBeenCalledTimes(1);
  });

  it("shows the waking notice after three seconds without mounting children", async () => {
    checkDatabaseHealth.mockImplementation((signal) => abortablePending(signal));

    render(
      <BackendReadinessGate>
        <div>Nội dung riêng tư</div>
      </BackendReadinessGate>,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(WAKE_NOTICE_DELAY_MS);
    });

    expect(screen.getByText(/khởi động máy chủ miễn phí/i)).toBeVisible();
    expect(screen.queryByText("Nội dung riêng tư")).not.toBeInTheDocument();
  });

  it("retries sequentially after a temporary failure and renders children", async () => {
    checkDatabaseHealth
      .mockRejectedValueOnce(new TypeError("cold start"))
      .mockResolvedValueOnce({ database: "connected" });

    render(
      <BackendReadinessGate>
        <div>Dashboard</div>
      </BackendReadinessGate>,
    );
    await flushPromises();
    expect(checkDatabaseHealth).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS);
    });

    expect(checkDatabaseHealth).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Dashboard")).toBeVisible();
  });

  it("does not overlap requests while an attempt is pending or before retry delay", async () => {
    checkDatabaseHealth
      .mockImplementationOnce((signal) => abortablePending(signal))
      .mockImplementationOnce((signal) => abortablePending(signal));

    render(
      <BackendReadinessGate>
        <div>Dashboard</div>
      </BackendReadinessGate>,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(ATTEMPT_TIMEOUT_MS - 1);
    });
    expect(checkDatabaseHealth).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
      await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS - 1);
    });
    expect(checkDatabaseHealth).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(checkDatabaseHealth).toHaveBeenCalledTimes(2);
  });

  it("shows unavailable state and manual retry after the deadline", async () => {
    checkDatabaseHealth.mockImplementation((signal) => abortablePending(signal));

    render(
      <BackendReadinessGate>
        <div>Dashboard</div>
      </BackendReadinessGate>,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(READINESS_DEADLINE_MS);
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Không thể kết nối tới máy chủ ParkSmart. Vui lòng kiểm tra kết nối và thử lại.",
    );
    expect(screen.getByRole("button", { name: "Thử lại" })).toBeVisible();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });

  it("starts a fresh cycle when the user retries", async () => {
    checkDatabaseHealth.mockImplementation((signal) => abortablePending(signal));

    render(
      <BackendReadinessGate>
        <div>Dashboard</div>
      </BackendReadinessGate>,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(READINESS_DEADLINE_MS);
    });

    checkDatabaseHealth.mockResolvedValue({ database: "connected" });
    fireEvent.click(screen.getByRole("button", { name: "Thử lại" }));
    expect(screen.getByText("Đang kết nối với ParkSmart AI…")).toBeVisible();
    await flushPromises();

    expect(screen.getByText("Dashboard")).toBeVisible();
  });

  it("aborts an active request and clears timers on unmount", () => {
    let requestSignal: AbortSignal | undefined;
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    checkDatabaseHealth.mockImplementation((signal) => {
      requestSignal = signal;
      return abortablePending(signal);
    });

    const view = render(
      <BackendReadinessGate>
        <div>Dashboard</div>
      </BackendReadinessGate>,
    );
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    view.unmount();

    expect(requestSignal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
    expect(consoleError).not.toHaveBeenCalled();
  });
});
