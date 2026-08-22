import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ParkingWorkflow } from "@/hooks/use-parking-workflow";
import {
  activeReservation,
  canonicalMap,
  currentLocation,
  parkingStatus,
} from "@/test/fixtures";

import Home from "./page";

const mocks = vi.hoisted(() => ({
  useParkSmartData: vi.fn(),
  useParkingWorkflow: vi.fn(),
  reportWrongParking: vi.fn(),
  routerReplace: vi.fn(),
  routerPush: vi.fn(),
  useAuth: vi.fn(),
  refreshProfile: vi.fn(),
  addVehicle: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mocks.routerReplace,
    push: mocks.routerPush,
  }),
}));
vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: mocks.useAuth,
  parkingIdentityFromProfile: (profile: {
    role: string;
    parking_user_id: string | null;
    default_vehicle_id: string | null;
  }) =>
    profile.role === "user" && profile.parking_user_id
      ? { userId: profile.parking_user_id, vehicleId: profile.default_vehicle_id }
      : null,
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
      addVehicle: mocks.addVehicle,
    },
  };
});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.clearAllMocks();
});

function mockAuthenticatedUser(vehicleId: string | null = "VEHICLE-A") {
  const profile = {
    id: "11111111-1111-4111-8111-111111111111",
    email: "user@example.com",
    full_name: "User",
    role: "user",
    parking_user_id: "USER-A",
    default_vehicle_id: vehicleId,
  };
  mocks.useAuth.mockReturnValue({
    status: "authenticated",
    profile,
    refreshProfile: mocks.refreshProfile,
  });
  return profile;
}

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

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function workflowWithReserveAction() {
  const workflow = workflowFixture();
  workflow.messages = [
    {
      id: "reserve-message",
      role: "agent",
      text: "Chá»n Ă´ F1-D01.",
      consumedActionIds: [],
      uiActions: [
        {
          id: "reserve-f1-d01",
          type: "RESERVE_AND_ROUTE",
          label: "Giá»¯ Ă´ F1-D01",
          payload: { slot_id: "F1-D01" },
          style: "primary",
          requires_confirmation: false,
        },
      ],
    },
  ];
  return workflow;
}

describe("authenticated user chat page", () => {
  it("renders the guest preview without authenticated parking-data hooks", async () => {
    const user = userEvent.setup();
    mocks.useAuth.mockReturnValue({
      status: "guest",
      profile: null,
      refreshProfile: mocks.refreshProfile,
    });

    render(<Home />);

    expect(screen.getByRole("heading", { name: "Tro ly ParkSmart" })).toBeVisible();
    expect(mocks.useParkSmartData).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Tim o do" }));
    expect(mocks.routerPush).toHaveBeenCalledWith("/login");
    expect(sessionStorage.getItem("parksmart-pending-intent")).toContain("find-parking");
  });

  it("passes the backend parking identity into data and workflow hooks", () => {
    mockAuthenticatedUser();
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
    mockAuthenticatedUser();
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
    mockAuthenticatedUser();
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

  it("preserves the active reservation arrival confirmation card", async () => {
    const user = userEvent.setup();
    mockAuthenticatedUser();
    const workflow = workflowFixture();
    workflow.currentLocationId = "F1-ENTRANCE";
    mocks.useParkSmartData.mockReturnValue(
      dataFixture({ activeReservation: { ...activeReservation, slot_id: "F1-A01" } }),
    );
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);

    expect(screen.getByRole("article", { name: "Chỗ đỗ đã giữ" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Tôi đã đến nơi" }));
    expect(workflow.confirmParking).toHaveBeenCalledTimes(1);
  });

  it("replays the exact vehicle-gated reserve action once after first vehicle creation", async () => {
    const user = userEvent.setup();
    mockAuthenticatedUser(null);
    const profileRefresh = deferred<ReturnType<typeof mockAuthenticatedUser>>();
    mocks.refreshProfile.mockReturnValue(profileRefresh.promise);
    mocks.addVehicle.mockResolvedValue({});
    const workflow = workflowWithReserveAction();
    workflow.messages = [
      {
        id: "reserve-message",
        role: "agent",
        text: "Chọn ô F1-D01.",
        consumedActionIds: [],
        uiActions: [
          {
            id: "reserve-f1-d01",
            type: "RESERVE_AND_ROUTE",
            label: "Giữ ô F1-D01",
            payload: { slot_id: "F1-D01" },
            style: "primary",
            requires_confirmation: false,
          },
        ],
      },
    ];
    mocks.useParkSmartData.mockReturnValue(dataFixture());
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    const view = render(<Home />);
    await user.click(screen.getByRole("button", { name: /F1-D01/ }));
    expect(screen.getByRole("dialog", { name: "Them xe dau tien" })).toBeVisible();
    expect(workflow.executeUiAction).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Bien so"), "51a12345");
    await user.click(screen.getByRole("button", { name: "Them xe" }));
    await waitFor(() => expect(mocks.refreshProfile).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Them xe dau tien" })).not.toBeInTheDocument(),
    );
    expect(workflow.executeUiAction).not.toHaveBeenCalled();

    const refreshedProfile = mockAuthenticatedUser("VEHICLE-NEW");
    profileRefresh.resolve(refreshedProfile);
    view.rerender(<Home />);
    expect(mocks.useParkingWorkflow).toHaveBeenLastCalledWith(
      expect.anything(),
      expect.anything(),
      { userId: "USER-A", vehicleId: "VEHICLE-NEW" },
    );

    expect(await screen.findByText("Chọn ô F1-D01.")).toBeVisible();
    await waitFor(() =>
      expect(workflow.executeUiAction).toHaveBeenCalledTimes(1),
    );
    expect(workflow.executeUiAction).toHaveBeenCalledWith(
      "reserve-message",
      expect.objectContaining({
        type: "RESERVE_AND_ROUTE",
        payload: { slot_id: "F1-D01" },
      }),
    );
    view.rerender(<Home />);
    view.rerender(<Home />);
    expect(workflow.executeUiAction).toHaveBeenCalledTimes(1);
  });

  it("does not reinsert the pending reserve action when refreshProfile races a vehicle identity render", async () => {
    const user = userEvent.setup();
    mockAuthenticatedUser(null);
    mocks.addVehicle.mockResolvedValue({});
    const workflow = workflowWithReserveAction();
    mocks.useParkSmartData.mockReturnValue(dataFixture());
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    const view = render(<Home />);
    mocks.refreshProfile.mockImplementation(async () => {
      const refreshedProfile = mockAuthenticatedUser("VEHICLE-NEW");
      view.rerender(<Home />);
      await waitFor(() =>
        expect(workflow.executeUiAction).toHaveBeenCalledTimes(1),
      );
      return refreshedProfile;
    });

    await user.click(screen.getByRole("button", { name: /F1-D01/ }));
    expect(screen.getByRole("dialog", { name: "Them xe dau tien" })).toBeVisible();
    expect(workflow.executeUiAction).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Bien so"), "51a12345");
    await user.click(screen.getByRole("button", { name: "Them xe" }));

    await waitFor(() => expect(mocks.refreshProfile).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Them xe dau tien" })).not.toBeInTheDocument(),
    );
    expect(mocks.useParkingWorkflow).toHaveBeenLastCalledWith(
      expect.anything(),
      expect.anything(),
      { userId: "USER-A", vehicleId: "VEHICLE-NEW" },
    );
    expect(workflow.executeUiAction).toHaveBeenCalledTimes(1);
    expect(workflow.executeUiAction).toHaveBeenCalledWith(
      "reserve-message",
      expect.objectContaining({
        type: "RESERVE_AND_ROUTE",
        payload: { slot_id: "F1-D01" },
      }),
    );

    view.rerender(<Home />);
    view.rerender(<Home />);
    expect(workflow.executeUiAction).toHaveBeenCalledTimes(1);
  });

  it("does not execute the pending reserve action when first vehicle creation fails", async () => {
    const user = userEvent.setup();
    mockAuthenticatedUser(null);
    mocks.addVehicle.mockRejectedValue(new Error("add vehicle failed"));
    const workflow = workflowWithReserveAction();
    mocks.useParkSmartData.mockReturnValue(dataFixture());
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    render(<Home />);

    await user.click(screen.getByRole("button", { name: /F1-D01/ }));
    await user.type(screen.getByLabelText("Bien so"), "51a12345");
    await user.click(screen.getByRole("button", { name: "Them xe" }));

    expect(await screen.findByRole("alert")).toBeVisible();
    expect(mocks.refreshProfile).not.toHaveBeenCalled();
    expect(workflow.executeUiAction).not.toHaveBeenCalled();
  });

  it("clears the pending reserve action when the first vehicle dialog is canceled", async () => {
    const user = userEvent.setup();
    mockAuthenticatedUser(null);
    const workflow = workflowWithReserveAction();
    mocks.useParkSmartData.mockReturnValue(dataFixture());
    mocks.useParkingWorkflow.mockReturnValue(workflow);

    const view = render(<Home />);

    await user.click(screen.getByRole("button", { name: /F1-D01/ }));
    expect(screen.getByRole("dialog", { name: "Them xe dau tien" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "x" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Them xe dau tien" })).not.toBeInTheDocument(),
    );
    expect(workflow.executeUiAction).not.toHaveBeenCalled();

    mockAuthenticatedUser("VEHICLE-NEW");
    view.rerender(<Home />);
    expect(workflow.executeUiAction).not.toHaveBeenCalled();
  });
});
