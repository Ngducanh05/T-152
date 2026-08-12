import {
  act,
  cleanup,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RouteOverlay } from "@/components/parking/RouteOverlay";
import { MVP_AGENT_THREAD_STORAGE_KEY } from "@/lib/demo";
import type { ParkSmartSnapshot } from "./use-parksmart-data";
import { useParkingWorkflow } from "./use-parking-workflow";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

describe("Agent structured route", () => {
  it("renders only the polyline returned in the structured chat response", async () => {
    sessionStorage.setItem(MVP_AGENT_THREAD_STORAGE_KEY, "thread-route");
    const snapshot: ParkSmartSnapshot = {
      map: { nodes: [], edges: [], slots: [] },
      slots: [],
      status: {
        total: 0,
        available: 0,
        reserved: 0,
        occupied: 0,
        by_zone: {
          A: { AVAILABLE: 0, RESERVED: 0, OCCUPIED: 0 },
          B: { AVAILABLE: 0, RESERVED: 0, OCCUPIED: 0 },
          C: { AVAILABLE: 0, RESERVED: 0, OCCUPIED: 0 },
          D: { AVAILABLE: 0, RESERVED: 0, OCCUPIED: 0 },
        },
      },
      currentLocation: { user_id: "USER-001", node_id: "F1-ENTRANCE" },
      activeReservation: null,
      activeSession: null,
    };
    const api = {
      confirmLocation: vi.fn(),
      recommend: vi.fn(),
      createReservation: vi.fn(),
      getRoute: vi.fn(),
      confirmParking: vi.fn(),
      getActiveSession: vi.fn(),
      completeSession: vi.fn(),
      resetDemo: vi.fn(),
      chat: vi.fn().mockResolvedValue({
        thread_id: "thread-route",
        message: "Không dùng đường 99,99 100,100 trong nội dung này.",
        intent: "route",
        selected_slot: "F1-D01",
        tool_names: ["get_route"],
        current_location: "F1-ENTRANCE",
        recommended_slot_ids: [],
        route: {
          path: ["F1-ENTRANCE", "F1-D01"],
          distance_m: 76,
          polyline: [
            [0, 50],
            [15, 50],
            [85, 25],
          ],
        },
      }),
    };
    const data = {
      slots: snapshot.slots,
      currentLocation: snapshot.currentLocation,
      activeReservation: null,
      activeSession: null,
      refresh: vi.fn(async () => snapshot),
    };
    const { result } = renderHook(() => useParkingWorkflow(data, api));
    await waitFor(() => expect(result.current.threadId).toBe("thread-route"));

    await act(async () => {
      await result.current.sendAgentMessage("Chỉ đường tới ô đã chọn");
    });
    render(
      <svg>
        <RouteOverlay route={result.current.activeRoute} />
      </svg>,
    );

    const points = screen.getByTestId("route-polyline").getAttribute("points");
    expect(points).toBe("0,50 15,50 85,25");
    expect(points).not.toContain("99,99");
  });
});
