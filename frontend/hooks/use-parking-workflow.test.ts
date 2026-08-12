import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { MVP_AGENT_THREAD_STORAGE_KEY } from "@/lib/demo";
import type { ChatResponse } from "@/lib/types";
import type { ParkSmartSnapshot } from "./use-parksmart-data";

import { useParkingWorkflow } from "./use-parking-workflow";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

function chatResponse(overrides: Partial<ChatResponse> = {}): ChatResponse {
  return {
    thread_id: "server-thread",
    message: "Đã xử lý yêu cầu.",
    intent: null,
    selected_slot: null,
    tool_names: [],
    current_location: null,
    recommended_slot_ids: [],
    route: null,
    ...overrides,
  };
}

function fixture() {
  const slot = {
    id: "F1-D01",
    floor_id: "F1" as const,
    zone_id: "D" as const,
    node_id: "F1-D-W",
    status: "AVAILABLE" as const,
    has_charger: true,
    is_accessible: false,
    version: 7,
    occupied_by_vehicle_id: null,
  };
  const snapshot: ParkSmartSnapshot = {
    map: { nodes: [], edges: [], slots: [slot] },
    slots: [slot],
    status: {
      total: 40,
      available: 40,
      reserved: 0,
      occupied: 0,
      by_zone: {
        A: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
        B: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
        C: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
        D: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
      },
    },
    currentLocation: { user_id: "USER-001", node_id: "F1-ENTRANCE" },
    activeReservation: null,
    activeSession: null,
  };
  const refresh = vi.fn(async () => snapshot);
  const data = {
    slots: snapshot.slots,
    currentLocation: snapshot.currentLocation,
    activeReservation: null,
    activeSession: null,
    refresh,
  };
  const recommendation = {
    recommendations: [
      {
        slot_id: slot.id,
        score: 92,
        distance_m: 76,
        reasons: ["Có sạc EV"],
      },
    ],
    parking_state_version: 1,
  };
  const api = {
    confirmLocation: vi.fn(),
    recommend: vi.fn(async () => recommendation),
    createReservation: vi.fn(),
    getRoute: vi.fn(),
    confirmParking: vi.fn(),
    getActiveSession: vi.fn(),
    completeSession: vi.fn(),
    resetDemo: vi.fn(),
    chat: vi.fn(),
  };
  return { api, data, refresh, slot };
}

describe("useParkingWorkflow", () => {
  it("highlights recommendations without selecting or reserving a slot", async () => {
    const { api, data, refresh, slot } = fixture();
    const { result } = renderHook(() => useParkingWorkflow(data, api));

    await act(async () => {
      await result.current.requestRecommendations({
        chargingRequired: true,
        accessibleRequired: false,
        nearElevator: true,
      });
    });

    expect(api.recommend).toHaveBeenCalledWith({
      user_id: "USER-001",
      start_node_id: "F1-ENTRANCE",
      charging_required: true,
      accessible_required: false,
      near_elevator: true,
      limit: 3,
    });
    expect(result.current.recommendedSlotIds).toEqual(["F1-D01"]);
    expect(result.current.selectedSlotId).toBeNull();
    expect(api.createReservation).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
    expect(slot.status).toBe("AVAILABLE");
  });

  it("uses the current slot version and never changes slot state on a failed reservation", async () => {
    const { api, data, refresh, slot } = fixture();
    api.createReservation.mockRejectedValue(
      new ApiError({
        code: "SLOT_NOT_AVAILABLE",
        message: "Slot version changed.",
        requestId: "request-conflict",
        status: 409,
      }),
    );
    const { result } = renderHook(() => useParkingWorkflow(data, api));

    await act(async () => {
      await result.current.requestRecommendations({
        chargingRequired: true,
        accessibleRequired: false,
        nearElevator: true,
      });
    });
    act(() => result.current.selectCandidate("F1-D01"));
    await act(async () => {
      await result.current.reserveSelected();
    });

    expect(api.createReservation).toHaveBeenCalledWith({
      user_id: "USER-001",
      vehicle_id: "VEHICLE-001",
      slot_id: "F1-D01",
      expected_version: 7,
    });
    expect(refresh).toHaveBeenCalledOnce();
    expect(slot.status).toBe("AVAILABLE");
    expect(result.current.selectedSlotId).toBeNull();
    expect(result.current.notice).toContain("hãy chọn một đề xuất còn AVAILABLE");
  });

  it("preserves the explicit selection when a non-conflict mutation fails", async () => {
    const { api, data, refresh, slot } = fixture();
    api.createReservation.mockRejectedValue(
      new ApiError({
        code: "AGENT_TOOL_UNAVAILABLE",
        message: "Service unavailable.",
        status: 503,
      }),
    );
    const { result } = renderHook(() => useParkingWorkflow(data, api));

    await act(async () => {
      await result.current.requestRecommendations({
        chargingRequired: true,
        accessibleRequired: false,
        nearElevator: true,
      });
    });
    act(() => result.current.selectCandidate("F1-D01"));
    await act(async () => {
      await result.current.reserveSelected();
    });

    expect(refresh).toHaveBeenCalledOnce();
    expect(slot.status).toBe("AVAILABLE");
    expect(result.current.selectedSlotId).toBe("F1-D01");
    expect(result.current.notice).toContain("AGENT_TOOL_UNAVAILABLE");
  });

  it("reuses one tab-scoped thread ID across multiple Agent turns", async () => {
    sessionStorage.setItem(MVP_AGENT_THREAD_STORAGE_KEY, "thread-this-tab");
    const { api, data } = fixture();
    api.chat.mockResolvedValue(chatResponse());
    const { result } = renderHook(() => useParkingWorkflow(data, api));
    await waitFor(() => expect(result.current.threadId).toBe("thread-this-tab"));

    await act(async () => {
      await result.current.sendAgentMessage("Tìm chỗ đỗ");
      await result.current.sendAgentMessage("Chỉ đường tới đó");
    });

    expect(api.chat).toHaveBeenNthCalledWith(1, {
      thread_id: "thread-this-tab",
      user_id: "USER-001",
      vehicle_id: "VEHICLE-001",
      message: "Tìm chỗ đỗ",
    });
    expect(api.chat).toHaveBeenNthCalledWith(2, {
      thread_id: "thread-this-tab",
      user_id: "USER-001",
      vehicle_id: "VEHICLE-001",
      message: "Chỉ đường tới đó",
    });
  });

  it("highlights only structured Agent recommendation IDs", async () => {
    sessionStorage.setItem(MVP_AGENT_THREAD_STORAGE_KEY, "thread-recommend");
    const { api, data } = fixture();
    api.chat.mockResolvedValue(
      chatResponse({
        message: "Tôi cũng có thể nhắc tới F1-A99 trong câu trả lời.",
        tool_names: ["recommend_parking_slot"],
        recommended_slot_ids: ["F1-D01"],
      }),
    );
    const { result } = renderHook(() => useParkingWorkflow(data, api));
    await waitFor(() => expect(result.current.threadId).toBe("thread-recommend"));

    await act(async () => {
      await result.current.sendAgentMessage("Tìm ô có sạc");
    });

    expect(result.current.recommendedSlotIds).toEqual(["F1-D01"]);
    expect(result.current.recommendedSlotIds).not.toContain("F1-A99");
    expect(result.current.selectedSlotId).toBeNull();
    expect(api.createReservation).not.toHaveBeenCalled();
  });

  it("refreshes authoritative resources after an Agent mutation", async () => {
    sessionStorage.setItem(MVP_AGENT_THREAD_STORAGE_KEY, "thread-mutation");
    const { api, data, refresh } = fixture();
    api.chat.mockResolvedValue(
      chatResponse({
        selected_slot: "F1-D01",
        tool_names: ["reserve_parking_slot"],
      }),
    );
    const { result } = renderHook(() => useParkingWorkflow(data, api));
    await waitFor(() => expect(result.current.threadId).toBe("thread-mutation"));

    await act(async () => {
      await result.current.sendAgentMessage("Giữ ô đã chọn");
    });

    expect(refresh).toHaveBeenCalledOnce();
    expect(result.current.selectedSlotId).toBe("F1-D01");
  });

  it("keeps the user turn and offers a safe retry on Agent 503", async () => {
    sessionStorage.setItem(MVP_AGENT_THREAD_STORAGE_KEY, "thread-retry");
    const { api, data } = fixture();
    api.chat.mockRejectedValue(
      new ApiError({
        code: "AGENT_TOOL_UNAVAILABLE",
        message: "internal tool traceback and prompt",
        status: 503,
      }),
    );
    const { result } = renderHook(() => useParkingWorkflow(data, api));
    await waitFor(() => expect(result.current.threadId).toBe("thread-retry"));

    await act(async () => {
      await result.current.sendAgentMessage("Tìm ô giúp tôi");
    });

    expect(result.current.messages).toEqual([
      { role: "user", text: "Tìm ô giúp tôi" },
    ]);
    expect(result.current.retryMessage).toBe("Tìm ô giúp tôi");
    expect(result.current.notice).toContain("thử gửi lại");
    expect(result.current.notice).not.toContain("traceback");
    expect(result.current.recommendedSlotIds).toEqual([]);
    expect(result.current.selectedSlotId).toBeNull();
    expect(result.current.activeRoute).toBeNull();
  });

  it("creates and persists a new Agent thread when resetting the demo", async () => {
    sessionStorage.setItem(MVP_AGENT_THREAD_STORAGE_KEY, "thread-before-reset");
    vi.spyOn(crypto, "randomUUID").mockReturnValue(
      "22222222-2222-4222-8222-222222222222",
    );
    const { api, data, refresh } = fixture();
    api.resetDemo.mockResolvedValue([]);
    const { result } = renderHook(() => useParkingWorkflow(data, api));
    await waitFor(() =>
      expect(result.current.threadId).toBe("thread-before-reset"),
    );

    await act(async () => {
      await result.current.resetDemo();
    });

    expect(result.current.threadId).toBe(
      "22222222-2222-4222-8222-222222222222",
    );
    expect(sessionStorage.getItem(MVP_AGENT_THREAD_STORAGE_KEY)).toBe(
      "22222222-2222-4222-8222-222222222222",
    );
    expect(result.current.messages).toEqual([]);
    expect(refresh).toHaveBeenCalledOnce();
  });
});
