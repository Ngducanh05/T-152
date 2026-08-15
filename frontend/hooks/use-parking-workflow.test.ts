import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { MVP_AGENT_THREAD_STORAGE_KEY } from "@/lib/demo";
import type { ChatResponse, SlotStatus } from "@/lib/types";
import { activeReservation } from "@/test/fixtures";
import type { ParkSmartSnapshot } from "./use-parksmart-data";

import { useParkingWorkflow, type WorkflowData } from "./use-parking-workflow";

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
  const data: WorkflowData = {
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
  it("confirms a slot location without reserving it or creating a parking session", async () => {
    const { api, data, refresh, slot } = fixture();
    api.confirmLocation.mockResolvedValue({
      user_id: "USER-001",
      node_id: "F1-D01",
    });
    const { result } = renderHook(() => useParkingWorkflow(data, api));

    await act(async () => {
      await result.current.confirmLocation("F1-D01");
    });

    expect(api.confirmLocation).toHaveBeenCalledOnce();
    expect(api.confirmLocation).toHaveBeenCalledWith({
      user_id: "USER-001",
      node_id: "F1-D01",
    });
    expect(refresh).toHaveBeenCalledOnce();
    expect(api.createReservation).not.toHaveBeenCalled();
    expect(api.confirmParking).not.toHaveBeenCalled();
    expect(api.getActiveSession).not.toHaveBeenCalled();
    expect(slot.status).toBe("AVAILABLE");
    expect(data.activeReservation).toBeNull();
    expect(data.activeSession).toBeNull();
  });

  it.each<SlotStatus>(["AVAILABLE", "RESERVED", "OCCUPIED"])(
    "does not change %s slot state locally when confirming location",
    async (status) => {
      const { api, data, slot } = fixture();
      (slot as { status: SlotStatus }).status = status;
      api.confirmLocation.mockResolvedValue({
        user_id: "USER-001",
        node_id: "F1-D01",
      });
      const { result } = renderHook(() => useParkingWorkflow(data, api));

      await act(async () => {
        await result.current.confirmLocation("F1-D01");
      });

      expect(slot.status).toBe(status);
      expect(api.confirmParking).not.toHaveBeenCalled();
    },
  );

  it("preserves backend location error code and request ID", async () => {
    const { api, data } = fixture();
    api.confirmLocation.mockRejectedValue(
      new ApiError({
        code: "LOCATION_NODE_NOT_FOUND",
        message: "Location node was not found.",
        requestId: "request-location-404",
        status: 404,
      }),
    );
    const { result } = renderHook(() => useParkingWorkflow(data, api));

    await act(async () => {
      await result.current.confirmLocation("F1-UNKNOWN");
    });

    expect(result.current.notice).toContain("LOCATION_NODE_NOT_FOUND");
    expect(result.current.notice).toContain("request-location-404");
    expect(api.confirmParking).not.toHaveBeenCalled();
  });

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
    expect(result.current.notice).toContain("hãy chọn một ô AVAILABLE khác");
  });

  it("allows selecting and reserving an available map slot outside recommendations", async () => {
    const { api, data, refresh } = fixture();
    const { result } = renderHook(() => useParkingWorkflow(data, api));

    act(() => result.current.selectCandidate("F1-D01"));
    await act(async () => {
      await result.current.reserveSelected();
    });

    expect(result.current.selectedSlotId).toBe("F1-D01");
    expect(result.current.recommendedSlotIds).toEqual([]);
    expect(api.createReservation).toHaveBeenCalledWith({
      user_id: "USER-001",
      vehicle_id: "VEHICLE-001",
      slot_id: "F1-D01",
      expected_version: 7,
    });
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("clears recommendation highlights after selecting and confirming a parking slot", async () => {
    const { api, data } = fixture();
    data.activeReservation = { ...activeReservation, slot_id: "F1-D01" };
    api.confirmParking.mockResolvedValue({
      id: "SESSION-001",
      user_id: "USER-001",
      vehicle_id: "VEHICLE-001",
      slot_id: "F1-D01",
      status: "ACTIVE",
      parked_at: "2026-08-13T04:00:00Z",
      completed_at: null,
    });
    const { result } = renderHook(() => useParkingWorkflow(data, api));

    await act(async () => {
      await result.current.requestRecommendations({
        chargingRequired: true,
        accessibleRequired: false,
        nearElevator: true,
      });
    });
    expect(result.current.recommendedSlotIds).toEqual(["F1-D01"]);

    act(() => result.current.selectCandidate("F1-D01"));
    expect(result.current.recommendedSlotIds).toEqual([]);

    await act(async () => {
      await result.current.confirmParking();
    });
    expect(result.current.recommendedSlotIds).toEqual([]);
    expect(result.current.candidates).toEqual([]);
  });

  it("waits for reservation success before refreshing authoritative UI state", async () => {
    const { api, data, refresh, slot } = fixture();
    let resolveReservation!: () => void;
    const reservationRequest = new Promise<void>((resolve) => {
      resolveReservation = resolve;
    });
    api.createReservation.mockImplementation(async () => {
      await reservationRequest;
      return activeReservation;
    });
    const { result } = renderHook(() => useParkingWorkflow(data, api));

    await act(async () => {
      await result.current.requestRecommendations({
        chargingRequired: true,
        accessibleRequired: false,
        nearElevator: true,
      });
    });
    act(() => result.current.selectCandidate("F1-D01"));

    let mutation!: Promise<void>;
    act(() => {
      mutation = result.current.reserveSelected();
    });
    expect(result.current.pending).toBe("reserve");
    expect(refresh).not.toHaveBeenCalled();
    expect(slot.status).toBe("AVAILABLE");

    await act(async () => {
      resolveReservation();
      await mutation;
    });

    expect(refresh).toHaveBeenCalledOnce();
    expect(result.current.pending).toBeNull();
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
      current_location: "F1-ENTRANCE",
      message: "Tìm chỗ đỗ",
    });
    expect(api.chat).toHaveBeenNthCalledWith(2, {
      thread_id: "thread-this-tab",
      user_id: "USER-001",
      vehicle_id: "VEHICLE-001",
      current_location: "F1-ENTRANCE",
      message: "Chỉ đường tới đó",
    });
  });

  it("returns the Agent response message after preserving structured UI effects", async () => {
    sessionStorage.setItem(MVP_AGENT_THREAD_STORAGE_KEY, "thread-response");
    const { api, data, refresh } = fixture();
    api.chat.mockResolvedValue(
      chatResponse({
        message: "Đã giữ ô F1-D01.",
        selected_slot: "F1-D01",
        current_location: "F1-ENTRANCE",
        tool_names: ["reserve_parking_slot"],
      }),
    );
    const { result } = renderHook(() => useParkingWorkflow(data, api));
    await waitFor(() => expect(result.current.threadId).toBe("thread-response"));

    let responseMessage: string | null = null;
    await act(async () => {
      responseMessage = await result.current.sendAgentMessage("Giữ ô này");
    });

    expect(responseMessage).toBe("Đã giữ ô F1-D01.");
    expect(result.current.selectedSlotId).toBe("F1-D01");
    expect(result.current.currentLocationId).toBe("F1-ENTRANCE");
    expect(result.current.lastToolNames).toEqual(["reserve_parking_slot"]);
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("returns null when the Agent request fails", async () => {
    sessionStorage.setItem(MVP_AGENT_THREAD_STORAGE_KEY, "thread-error");
    const { api, data } = fixture();
    api.chat.mockRejectedValue(
      new ApiError({
        code: "AGENT_TOOL_UNAVAILABLE",
        message: "Agent unavailable.",
        status: 503,
      }),
    );
    const { result } = renderHook(() => useParkingWorkflow(data, api));
    await waitFor(() => expect(result.current.threadId).toBe("thread-error"));

    let responseMessage: string | null = "unexpected";
    await act(async () => {
      responseMessage = await result.current.sendAgentMessage("Tìm ô giúp tôi");
    });

    expect(responseMessage).toBeNull();
    expect(result.current.notice).toContain("thử gửi lại");
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
    expect(result.current.lastToolNames).toEqual(["recommend_parking_slot"]);
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

  it("keeps the current thread and chat when the backend reset fails", async () => {
    sessionStorage.setItem(MVP_AGENT_THREAD_STORAGE_KEY, "thread-before-failure");
    const { api, data } = fixture();
    api.chat.mockResolvedValue(chatResponse({ message: "Tin nhắn còn lại." }));
    api.resetDemo.mockRejectedValue(
      new ApiError({
        code: "INVALID_TRANSITION",
        message: "Demo reset is disabled.",
        requestId: "request-reset-disabled",
        status: 400,
      }),
    );
    const { result } = renderHook(() => useParkingWorkflow(data, api));
    await waitFor(() =>
      expect(result.current.threadId).toBe("thread-before-failure"),
    );
    await act(async () => {
      await result.current.sendAgentMessage("Giữ lại hội thoại này");
    });

    await act(async () => {
      await result.current.resetDemo();
    });

    expect(result.current.threadId).toBe("thread-before-failure");
    expect(sessionStorage.getItem(MVP_AGENT_THREAD_STORAGE_KEY)).toBe(
      "thread-before-failure",
    );
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.notice).toContain("Mã lỗi: INVALID_TRANSITION");
    expect(result.current.notice).toContain("Mã yêu cầu: request-reset-disabled");
  });
});
