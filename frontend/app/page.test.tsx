import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import type { ParkingWorkflow } from "@/hooks/use-parking-workflow";
import { canonicalMap, currentLocation, parkingStatus } from "@/test/fixtures";

import Home from "./page";

const mocks = vi.hoisted(() => ({
  useParkSmartData: vi.fn(),
  useParkingWorkflow: vi.fn(),
  reportWrongParking: vi.fn(),
}));

vi.mock("@/components/auth/ProtectedRoute", () => ({
  ProtectedRoute: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({
    status: "authenticated",
    profile: {
      id: "11111111-1111-4111-8111-111111111111",
      email: "user@example.com",
      full_name: "User",
      role: "user",
      parking_user_id: "USER-A",
      default_vehicle_id: "VEHICLE-A",
    },
  }),
  parkingIdentityFromProfile: () => ({ userId: "USER-A", vehicleId: "VEHICLE-A" }),
}));
vi.mock("@/components/auth/LogoutButton", () => ({
  LogoutButton: () => <button type="button">Đăng xuất</button>,
}));
vi.mock("@/hooks/use-parksmart-data", () => ({
  useParkSmartData: mocks.useParkSmartData,
}));
vi.mock("@/hooks/use-parking-workflow", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-parking-workflow")>();
  return { ...actual, useParkingWorkflow: mocks.useParkingWorkflow };
});
vi.mock("@/components/assistant/AgentComposer", () => ({
  AgentComposer: () => <div data-testid="agent-composer" />,
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    parkSmartApi: {
      ...actual.parkSmartApi,
      reportWrongParking: mocks.reportWrongParking,
    },
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function workflowFixture(): ParkingWorkflow {
  const welcomeAction = {
    id: "welcome-find-parking",
    type: "SELECT_PARKING_PREFERENCE" as const,
    label: "Tìm ô đỗ",
    payload: { preference: "ANY" as const },
    style: "primary" as const,
    requires_confirmation: false,
  };
  return {
    candidates: [],
    recommendedSlotIds: [],
    selectedSlotId: null,
    activeRoute: null,
    currentLocationId: "F1-ENTRANCE",
    lastToolNames: [],
    messages: [
      {
        id: "welcome",
        role: "agent",
        text: "Chào bạn!",
        uiActions: [welcomeAction],
        consumedActionIds: [],
      },
    ],
    threadId: "thread-test",
    pending: null,
    pendingAdjacentSlotId: null,
    notice: null,
    retryMessage: null,
    requestedPanel: null,
    selectCandidate: vi.fn(),
    clearRoute: vi.fn(),
    confirmLocation: vi.fn(async () => true),
    requestRecommendations: vi.fn(async () => undefined),
    reserveSelected: vi.fn(async () => undefined),
    reserveSelectedAndRoute: vi.fn(async () => undefined),
    cancelActiveReservation: vi.fn(async () => undefined),
    requestRouteToSelected: vi.fn(async () => undefined),
    confirmParking: vi.fn(async () => undefined),
    findVehicleAndRoute: vi.fn(async () => undefined),
    completeSession: vi.fn(async () => undefined),
    updateAdjacentSlotStatus: vi.fn(async () => undefined),
    resetDemo: vi.fn(async () => undefined),
    sendAgentMessage: vi.fn(async () => null),
    retryAgentMessage: vi.fn(async () => undefined),
    executeUiAction: vi.fn(async () => undefined),
    clearRequestedPanel: vi.fn(),
  };
}

function dataFixture(overrides: Record<string, unknown> = {}) {
  return {
    map: canonicalMap,
    slots: canonicalMap.slots,
    status: parkingStatus,
    currentLocation,
    activeReservation: null,
    activeSession: null,
    lastUpdatedAt: null,
    loading: false,
    refreshing: false,
    error: null,
    refresh: vi.fn(),
    ...overrides,
  };
}

describe("authenticated user chat page", () => {
  it("passes the backend parking identity into data and workflow hooks", () => {
    const workflow = workflowFixture();
    mocks.useParkSmartData.mockReturnValue(dataFixture());
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);

    expect(mocks.useParkSmartData).toHaveBeenCalledWith(
      expect.anything(),
      "USER-A",
    );
    expect(mocks.useParkingWorkflow).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      { userId: "USER-A", vehicleId: "VEHICLE-A" },
    );
    expect(screen.getByRole("button", { name: "Đăng xuất" })).toBeVisible();
  });

  it("shows welcome actions and keeps the user page map-free", async () => {
    const user = userEvent.setup();
    const workflow = workflowFixture();
    mocks.useParkSmartData.mockReturnValue(dataFixture());
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);

    expect(screen.queryByTestId("parking-map")).not.toBeInTheDocument();
    const action = screen.getByRole("button", { name: "Tìm ô đỗ" });
    expect(action).toBeVisible();
    await user.click(action);
    expect(workflow.executeUiAction).toHaveBeenCalledWith(
      "welcome",
      expect.objectContaining({ id: "welcome-find-parking" }),
    );
  });

  it("keeps active-session controls available", async () => {
    const user = userEvent.setup();
    const workflow = workflowFixture();
    mocks.useParkSmartData.mockReturnValue(
      dataFixture({
        activeSession: {
          session_id: "SESSION-001",
          vehicle_id: "VEHICLE-A",
          slot_id: "F1-D03",
          destination_node_id: "F1-D03",
        },
      }),
    );
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);

    expect(
      screen.getByRole("article", { name: "Xe đang đỗ trong bãi" }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Báo F1-D02 đang trống" }));
    expect(workflow.updateAdjacentSlotStatus).toHaveBeenCalledWith(
      "F1-D02",
      "AVAILABLE",
    );
  });
});
