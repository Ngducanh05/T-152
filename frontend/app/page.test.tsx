import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ParkingWorkflow } from "@/hooks/use-parking-workflow";
import { canonicalMap, currentLocation, parkingStatus } from "@/test/fixtures";

import Home from "./page";

const mocks = vi.hoisted(() => ({
  useParkSmartData: vi.fn(),
  useParkingWorkflow: vi.fn(),
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
vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({
    profile: {
      id: "auth-user-001",
      email: "user@example.com",
      full_name: "Test User",
      role: "user",
      parking_user_id: "USER-001",
      default_vehicle_id: "VEHICLE-001",
    },
    refreshProfile: vi.fn(async () => null),
  }),
  parkingIdentityFromProfile: () => ({
    userId: "USER-001",
    vehicleId: "VEHICLE-001",
  }),
}));
vi.mock("@/components/auth/ProtectedRoute", () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/components/auth/LogoutButton", () => ({
  LogoutButton: () => <button type="button">Đăng xuất</button>,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllEnvs();
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
    messages: [{
      id: "welcome",
      role: "agent",
      text: "Chào bạn!",
      uiActions: [welcomeAction],
      consumedActionIds: [],
    }],
    threadId: "thread-test",
    pending: null,
    pendingAdjacentSlotId: null,
    notice: null,
    retryMessage: null,
    requestedPanel: null,
    selectCandidate: vi.fn(),
    clearRoute: vi.fn(),
    confirmLocation: vi.fn(async () => true),
    requestRecommendations: vi.fn(async () => true),
    reserveSelected: vi.fn(async () => undefined),
    reserveSelectedAndRoute: vi.fn(async () => true),
    cancelActiveReservation: vi.fn(async () => true),
    requestRouteToSelected: vi.fn(async () => undefined),
    requestRouteToActiveReservation: vi.fn(async () => true),
    confirmParking: vi.fn(async () => true),
    findVehicleAndRoute: vi.fn(async () => undefined),
    completeSession: vi.fn(async () => true),
    updateAdjacentSlotStatus: vi.fn(async () => null),
    resetDemo: vi.fn(async () => undefined),
    sendAgentMessage: vi.fn(async () => null),
    retryAgentMessage: vi.fn(async () => undefined),
    executeUiAction: vi.fn(async () => undefined),
    clearRequestedPanel: vi.fn(),
  };
}

describe("user chat page", () => {
  it("renders the Agent composer when Agent is enabled", () => {
    vi.stubEnv("NEXT_PUBLIC_AGENT_ENABLED", "true");
    const workflow = workflowFixture();
    mocks.useParkSmartData.mockReturnValue({
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
    });
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);

    expect(screen.getByTestId("agent-composer")).toBeVisible();
  });

  it("replaces the Agent composer with the public fallback when disabled", () => {
    vi.stubEnv("NEXT_PUBLIC_AGENT_ENABLED", "false");
    const workflow = workflowFixture();
    mocks.useParkSmartData.mockReturnValue({
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
    });
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);

    expect(screen.queryByTestId("agent-composer")).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Trợ lý AI hiện đang tạm tắt. Bạn vẫn có thể sử dụng các thao tác tìm chỗ, giữ chỗ và báo sự cố.",
      ),
    ).toBeVisible();
  });

  it("does not render ParkingMap or operational summaries and shows welcome actions", async () => {
    const user = userEvent.setup();
    const workflow = workflowFixture();
    mocks.useParkSmartData.mockReturnValue({
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
    });
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);
    expect(screen.queryByTestId("parking-map")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Tóm tắt trạng thái bãi xe")).not.toBeInTheDocument();
    expect(document.querySelector(".sidebar")).toBeNull();
    const action = screen.getByRole("button", { name: "Tìm ô đỗ" });
    expect(action).toBeVisible();
    expect(action.closest("article")).toHaveTextContent("Chào bạn!");

    await user.click(action);
    expect(workflow.executeUiAction).toHaveBeenCalledWith(
      "welcome",
      expect.objectContaining({ id: "welcome-find-parking" }),
    );
  });

  it("renders the manual LocationPicker without any QR scanner", () => {
    const workflow = workflowFixture();
    workflow.requestedPanel = { kind: "location" };
    mocks.useParkSmartData.mockReturnValue({
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
    });
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);
    expect(screen.getByText("Vị trí trong bãi")).toBeVisible();
    expect(
      screen.getByRole("dialog", { name: "Xác nhận vị trí hiện tại" }),
    ).toBeVisible();
    expect(screen.queryByTestId("location-qr-scanner")).not.toBeInTheDocument();
  });

  it("confirms parking directly instead of opening the location picker", async () => {
    const user = userEvent.setup();
    const workflow = workflowFixture();
    mocks.useParkSmartData.mockReturnValue({
      map: canonicalMap,
      slots: canonicalMap.slots,
      status: parkingStatus,
      currentLocation,
      activeReservation: {
        id: "RESERVATION-001",
        user_id: "USER-001",
        vehicle_id: "VEHICLE-001",
        slot_id: "F1-D01",
        status: "ACTIVE",
        created_at: "2026-08-19T04:00:00Z",
        expires_at: "2026-08-19T04:05:00Z",
      },
      activeSession: null,
      lastUpdatedAt: null,
      loading: false,
      refreshing: false,
      error: null,
      refresh: vi.fn(),
    });
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);
    await user.click(screen.getByRole("button", { name: "Xác nhận đã đỗ" }));

    expect(workflow.confirmParking).toHaveBeenCalledOnce();
    expect(
      screen.queryByRole("dialog", { name: "Xác nhận vị trí hiện tại" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chỉ đường tới ô" })).toBeVisible();
  });

  it("keeps active-session controls in the priority dock and offers adjacent updates", async () => {
    const user = userEvent.setup();
    const workflow = workflowFixture();
    mocks.useParkSmartData.mockReturnValue({
      map: canonicalMap,
      slots: canonicalMap.slots,
      status: parkingStatus,
      currentLocation,
      activeReservation: null,
      activeSession: {
        session_id: "SESSION-001",
        vehicle_id: "VEHICLE-001",
        slot_id: "F1-D03",
        destination_node_id: "F1-D03",
      },
      lastUpdatedAt: null,
      loading: false,
      refreshing: false,
      error: null,
      refresh: vi.fn(),
    });
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);
    const dock = screen.getByRole("region", {
      name: "Thông tin và thao tác quan trọng",
    });
    expect(dock).toHaveClass("conversation-priority-dock");
    expect(screen.getByText("Vị trí đỗ xe")).toBeVisible();
    expect(screen.getAllByText("Ô D03 — Tầng 1 (F1-D03)")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /Vị trí trong bãi/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chỉ đường tới xe" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Kết thúc phiên" })).toBeVisible();
    expect(dock).toContainElement(
      screen.getByRole("article", { name: "Xe đang đỗ trong bãi" }),
    );
    await user.click(screen.getByRole("button", { name: "Giúp kiểm tra ngay" }));
    await user.click(screen.getByRole("button", { name: "Ô đang trống" }));
    expect(workflow.updateAdjacentSlotStatus).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Gửi đóng góp" }));
    expect(workflow.updateAdjacentSlotStatus).toHaveBeenCalledWith(
      "F1-D02",
      "AVAILABLE",
      undefined,
    );
  });

  it("opens the mounted Points dialog from the header and caps the badge", async () => {
    const user = userEvent.setup();
    const workflow = workflowFixture();
    mocks.useParkSmartData.mockReturnValue({
      map: canonicalMap,
      slots: canonicalMap.slots,
      status: parkingStatus,
      currentLocation,
      activeReservation: null,
      activeSession: null,
      rewardSummary: {
        available_points: 1200,
        pending_points: 0,
        verified_contributions: 0,
        daily_pending_points: 0,
        daily_earned_points: 0,
        daily_limit_points: 100,
      },
      rewardConfiguration: {
        adjacent_observation_reward_points: 10,
        wrong_parking_report_reward_points: 20,
        contribution_daily_points_limit: 100,
        redemption_enabled: false,
      },
      contributions: [],
      rewardCatalog: [],
      vouchers: [],
      rewardLedger: [],
      rewardLedgerAvailable: true,
      lastUpdatedAt: null,
      loading: false,
      refreshing: false,
      error: null,
      refresh: vi.fn(async () => undefined),
    });
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);
    const trigger = screen.getByRole("button", {
      name: "ParkSmart Points: 1200 điểm",
    });
    expect(trigger).toHaveTextContent("999+");
    expect(trigger.closest("header")).toHaveClass("chat-app-header");
    expect(screen.queryByRole("dialog", { name: "Điểm và voucher của bạn" })).not.toBeInTheDocument();

    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Điểm và voucher của bạn" });
    expect(dialog).toBeVisible();
    expect(document.querySelector(".chat-conversation")).not.toContainElement(dialog);
    await user.click(screen.getByRole("button", { name: "Đóng ParkSmart Points" }));
    expect(screen.queryByRole("dialog", { name: "Điểm và voucher của bạn" })).not.toBeInTheDocument();
  });
});
