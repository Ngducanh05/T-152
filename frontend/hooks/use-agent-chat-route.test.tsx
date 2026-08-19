import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RouteOverlay } from "@/components/parking/RouteOverlay";
import { MVP_AGENT_THREAD_STORAGE_KEY } from "@/lib/demo";
import {
  agentChatResponse,
  canonicalMap,
  currentLocation,
  parkingStatus,
} from "@/test/fixtures";
import type { ParkSmartSnapshot } from "./use-parksmart-data";
import { useParkingWorkflow } from "./use-parking-workflow";

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

describe("Agent structured UI effects", () => {
  it("shows structured selection and renders only the backend route polyline", async () => {
    sessionStorage.setItem(MVP_AGENT_THREAD_STORAGE_KEY, "thread-route");
    const snapshot: ParkSmartSnapshot = {
      map: canonicalMap,
      slots: canonicalMap.slots,
      status: parkingStatus,
      currentLocation,
      activeReservation: null,
      activeSession: null,
    };
    const api = {
      confirmLocation: vi.fn(),
      recommend: vi.fn(),
    createReservation: vi.fn(),
    cancelReservation: vi.fn(),
      getRoute: vi.fn(),
      confirmParking: vi.fn(),
      getActiveSession: vi.fn(),
      completeSession: vi.fn(),
      observeAdjacentSlot: vi.fn(),
      resetDemo: vi.fn(),
      chat: vi.fn().mockResolvedValue({
        ...agentChatResponse,
        message: "Không dùng đường 99,99 100,100 trong nội dung này.",
      }),
    };
    const data = {
      slots: snapshot.slots,
      currentLocation: snapshot.currentLocation,
      activeReservation: null,
      activeSession: null,
      refresh: vi.fn(async () => snapshot),
    };

    function AgentHarness() {
      const workflow = useParkingWorkflow(data, api);
      return (
        <div>
          <button
            disabled={!workflow.threadId || workflow.pending === "chat"}
            onClick={() => void workflow.sendAgentMessage("Chỉ đường")}
          >
            Gửi Agent
          </button>
          <p>Đề xuất: {workflow.recommendedSlotIds.join(", ") || "chưa có"}</p>
          <p>Đã chọn: {workflow.selectedSlotId ?? "chưa có"}</p>
          <p>Vị trí: {workflow.currentLocationId ?? "chưa có"}</p>
          <p>Công cụ: {workflow.lastToolNames.join(", ") || "chưa có"}</p>
          <svg>
            <RouteOverlay route={workflow.activeRoute} />
          </svg>
        </div>
      );
    }

    const user = userEvent.setup();
    render(<AgentHarness />);
    const send = screen.getByRole("button", { name: "Gửi Agent" });
    await waitFor(() => expect(send).toBeEnabled());
    await user.click(send);

    expect(await screen.findByText("Đề xuất: F1-D01")).toBeVisible();
    expect(screen.getByText("Đã chọn: F1-D01")).toBeVisible();
    expect(screen.getByText("Vị trí: F1-ENTRANCE")).toBeVisible();
    expect(
      screen.getByText("Công cụ: recommend_parking_slot, get_route"),
    ).toBeVisible();
    const points = screen.getByTestId("route-polyline").getAttribute("points");
    expect(points).toBe("0,50 15,50 58,70 58,74");
    expect(points).not.toContain("99,99");
  });
});
