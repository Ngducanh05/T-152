"use client";

import { useEffect, useRef, useState } from "react";

import type { ParkSmartData, ParkSmartSnapshot } from "@/hooks/use-parksmart-data";
import {
  ApiError,
  formatApiErrorForOperator,
  parkSmartApi,
  type ParkSmartApiClient,
} from "@/lib/api";
import {
  clearIdempotencyKey,
  getOrCreateIdempotencyKey,
  type IdempotencyAttempt,
} from "@/lib/idempotency";
import {
  getOrCreateThreadId,
  MVP_DEMO_PARKING_IDENTITY,
  rotateThreadId,
} from "@/lib/demo";
import type { ParkingIdentity } from "@/lib/auth";
import { isAgentEnabled } from "@/lib/public-config";
import { formatParkingLocation } from "@/lib/parking-display";
import type {
  ChatUiAction,
  AdjacentSlotObservedStatus,
  FloorScopedId,
  ParkingPreference,
  RecommendationCandidate,
  RouteResult,
  ParkingSessionCompletion,
  SlotObservation,
} from "@/lib/types";

export type WorkflowAction =
  | "location"
  | "recommend"
  | "reserve"
  | "reserve-and-route"
  | "cancel-reservation"
  | "route"
  | "confirm-parking"
  | "find-car"
  | "complete-session"
  | "observe-adjacent-slot"
  | "reset"
  | "chat";

export interface WorkflowMessage {
  id: string;
  role: "agent" | "user";
  text: string;
  uiActions: ChatUiAction[];
  consumedActionIds: string[];
}

export type WorkflowPanelRequest =
  | { kind: "location"; purpose?: "find-vehicle" }
  | { kind: "wrong-parking-report"; slotId: FloorScopedId | null };

type WorkflowApi = Pick<
  ParkSmartApiClient,
  | "confirmLocation"
  | "recommend"
  | "createReservation"
  | "cancelReservation"
  | "getRoute"
  | "confirmParking"
  | "getActiveSession"
  | "completeSession"
  | "resetDemo"
  | "chat"
  | "observeAdjacentSlot"
>;

export interface WorkflowData
  extends Pick<
    ParkSmartData,
    "slots" | "currentLocation" | "activeReservation" | "activeSession"
  > {
  refresh: () => Promise<ParkSmartSnapshot>;
  applyCurrentLocation?: ParkSmartData["applyCurrentLocation"];
}

export interface ParkingWorkflow {
  candidates: RecommendationCandidate[];
  recommendedSlotIds: FloorScopedId[];
  selectedSlotId: FloorScopedId | null;
  activeRoute: RouteResult | null;
  currentLocationId: FloorScopedId | null;
  lastToolNames: string[];
  messages: WorkflowMessage[];
  threadId: string | null;
  pending: WorkflowAction | null;
  pendingAdjacentSlotId: FloorScopedId | null;
  notice: string | null;
  retryMessage: string | null;
  requestedPanel: WorkflowPanelRequest | null;
  selectCandidate: (slotId: FloorScopedId) => void;
  clearRoute: () => void;
  confirmLocation: (nodeId: FloorScopedId) => Promise<boolean>;
  requestRecommendations: (preferences: {
    chargingRequired: boolean;
    accessibleRequired: boolean;
    nearElevator: boolean;
  }) => Promise<boolean>;
  reserveSelected: () => Promise<void>;
  reserveSelectedAndRoute: (slotId?: FloorScopedId) => Promise<boolean>;
  cancelActiveReservation: () => Promise<boolean>;
  requestRouteToSelected: () => Promise<void>;
  requestRouteToActiveReservation: () => Promise<boolean>;
  confirmParking: () => Promise<boolean>;
  findVehicleAndRoute: () => Promise<void>;
  completeSession: () => Promise<boolean>;
  updateAdjacentSlotStatus: (
    slotId: FloorScopedId,
    status: AdjacentSlotObservedStatus,
    evidence?: File | null,
  ) => Promise<SlotObservation | null>;
  resetDemo: () => Promise<void>;
  sendAgentMessage: (message: string) => Promise<string | null>;
  retryAgentMessage: () => Promise<void>;
  executeUiAction: (
    messageId: string,
    action: ChatUiAction,
  ) => Promise<void>;
  clearRequestedPanel: () => void;
}

function vietnameseError(error: unknown) {
  return formatApiErrorForOperator(error);
}

function isSlotConflict(error: unknown) {
  return error instanceof ApiError && error.code === "SLOT_NOT_AVAILABLE";
}

function isDefinitiveMutationRejection(error: unknown) {
  return (
    error instanceof ApiError &&
    error.status >= 400 &&
    error.status < 500
  );
}

function formatDisplayMinutes(value: number): string {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(value);
}

function completionNotice(completion: ParkingSessionCompletion, refreshFailed = false): string {
  const benefit = completion.time_benefit;
  const refreshNote = refreshFailed ? " Dữ liệu mới nhất chưa thể tải lại." : "";
  if (!benefit.voucher_id) return `Phiên đỗ xe đã kết thúc.${refreshNote}`;
  return `Phiên đỗ xe đã kết thúc. Tổng thời gian ${formatDisplayMinutes(benefit.total_minutes)} phút; áp dụng miễn phí ${formatDisplayMinutes(benefit.free_minutes)} phút; thời gian còn lại ${formatDisplayMinutes(benefit.billable_minutes)} phút.${refreshNote}`;
}

const AUTHORITATIVE_REFRESH_TOOLS = new Set([
  "get_parking_status",
  "reserve_parking_slot",
  "set_user_location",
  "confirm_parking",
  "find_parked_vehicle",
  "cancel_reservation",
  "complete_parking_session",
]);

const KNOWN_UI_ACTION_TYPES = new Set([
  "SELECT_LOCATION",
  "SELECT_PARKING_PREFERENCE",
  "SELECT_SLOT",
  "RESERVE_AND_ROUTE",
  "CONFIRM_PARKING",
  "FIND_VEHICLE",
  "COMPLETE_SESSION",
  "OPEN_WRONG_PARKING_REPORT",
  "CANCEL",
]);

const REPEATABLE_UI_ACTION_TYPES = new Set<ChatUiAction["type"]>([
  "SELECT_LOCATION",
  "SELECT_SLOT",
  "FIND_VEHICLE",
  "OPEN_WRONG_PARKING_REPORT",
]);

const WELCOME_ACTIONS: ChatUiAction[] = [
  {
    id: "welcome-find-parking",
    type: "SELECT_PARKING_PREFERENCE",
    label: "Tìm ô đỗ",
    payload: { preference: "ANY" },
    style: "primary",
    requires_confirmation: false,
  },
  {
    id: "welcome-find-vehicle",
    type: "FIND_VEHICLE",
    label: "Xe của tôi",
    payload: {},
    style: "secondary",
    requires_confirmation: false,
  },
  {
    id: "welcome-location",
    type: "SELECT_LOCATION",
    label: "Xác nhận vị trí",
    payload: {},
    style: "secondary",
    requires_confirmation: false,
  },
  {
    id: "welcome-report",
    type: "OPEN_WRONG_PARKING_REPORT",
    label: "Báo xe đỗ sai",
    payload: {},
    style: "danger",
    requires_confirmation: false,
  },
];

function welcomeMessage(): WorkflowMessage {
  return {
    id: "welcome",
    role: "agent",
    text: "Chào bạn! Tôi có thể giúp tìm chỗ đỗ, chỉ đường hoặc tìm lại xe.",
    uiActions: WELCOME_ACTIONS,
    consumedActionIds: [],
  };
}

function preferencesFor(value: ParkingPreference) {
  return {
    chargingRequired: value === "EV",
    accessibleRequired: value === "ACCESSIBLE",
    nearElevator: value === "NEAR_ELEVATOR",
  };
}

export function useParkingWorkflow(
  data: WorkflowData,
  api: WorkflowApi = parkSmartApi,
  identity: ParkingIdentity = MVP_DEMO_PARKING_IDENTITY,
): ParkingWorkflow {
  const [candidates, setCandidates] = useState<RecommendationCandidate[]>([]);
  const [recommendedSlotIds, setRecommendedSlotIds] = useState<FloorScopedId[]>([]);
  const [selectedSlotId, setSelectedSlotId] = useState<FloorScopedId | null>(null);
  const [activeRoute, setActiveRoute] = useState<RouteResult | null>(null);
  const [agentCurrentLocationId, setAgentCurrentLocationId] =
    useState<FloorScopedId | null>(null);
  const [lastToolNames, setLastToolNames] = useState<string[]>([]);
  const [messages, setMessages] = useState<WorkflowMessage[]>([welcomeMessage()]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [pending, setPending] = useState<WorkflowAction | null>(null);
  const [pendingAdjacentSlotId, setPendingAdjacentSlotId] =
    useState<FloorScopedId | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [retryMessage, setRetryMessage] = useState<string | null>(null);
  const [requestedPanel, setRequestedPanel] =
    useState<WorkflowPanelRequest | null>(null);
  const chatInFlightRef = useRef(false);
  const actionInFlightRef = useRef(new Set<string>());
  const reserveAndRouteInFlightRef = useRef(false);
  const adjacentObservationInFlightRef = useRef(false);
  const deferredPreferenceRef = useRef<ParkingPreference | null>(null);
  const deferredFindVehicleRef = useRef(false);
  const deferredReservationRouteRef = useRef(false);
  const reservationIdempotencyRef = useRef<IdempotencyAttempt | null>(null);
  const confirmParkingIdempotencyRef = useRef<IdempotencyAttempt | null>(null);
  const completeSessionIdempotencyRef = useRef<IdempotencyAttempt | null>(null);
  const messageSequenceRef = useRef(0);

  function nextMessageId(role: WorkflowMessage["role"]) {
    messageSequenceRef.current += 1;
    return `${role}-${messageSequenceRef.current}`;
  }

  function appendAgentMessage(text: string, uiActions: ChatUiAction[] = []) {
    setMessages((current) => [
      ...current,
      {
        id: nextMessageId("agent"),
        role: "agent",
        text,
        uiActions: uiActions.slice(0, 5),
        consumedActionIds: [],
      },
    ]);
  }

  function slotSelectionActions(
    recommendations: RecommendationCandidate[],
  ): ChatUiAction[] {
    return recommendations.slice(0, 3).map((candidate) => ({
      id: `select-slot:${candidate.slot_id.toLowerCase()}`,
      type: "SELECT_SLOT" as const,
      label: `Chọn ${candidate.slot_id}`,
      payload: { slot_id: candidate.slot_id },
      style: "primary" as const,
      requires_confirmation: false,
    }));
  }

  function preferenceIsAvailable(preference: ParkingPreference) {
    return preference !== "ACCESSIBLE" || data.slots.some((slot) => slot.is_accessible);
  }

  function noRecommendationMessage(preference: ParkingPreference) {
    if (preference === "EV") return "Hiện chưa có ô có sạc phù hợp đang trống.";
    if (preference === "NEAR_ELEVATOR") return "Hiện chưa tìm được ô phù hợp gần thang máy.";
    if (preference === "ACCESSIBLE") return "Hiện chưa có ô hỗ trợ nhu cầu tiếp cận phù hợp đang trống.";
    return "Hiện chưa có ô phù hợp đang trống.";
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setThreadId(getOrCreateThreadId(identity.userId));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [identity.userId]);

  async function refreshQuietly() {
    try {
      return await data.refresh();
    } catch {
      return null;
    }
  }

  async function handleMutationFailure(error: unknown) {
    await refreshQuietly();
    if (isSlotConflict(error)) {
      setSelectedSlotId(null);
      setActiveRoute(null);
      setNotice(
        formatApiErrorForOperator(
          error,
          "Ô vừa thay đổi hoặc không còn trống. Thông tin đã được tải lại; hãy chọn một ô đang trống khác và thử lại.",
        ),
      );
      return;
    }
    setNotice(vietnameseError(error));
  }

  function clearRecommendations() {
    setCandidates([]);
    setRecommendedSlotIds([]);
  }

  function selectCandidate(slotId: FloorScopedId) {
    if (!data.slots.some((slot) => slot.id === slotId)) return;
    clearRecommendations();
    setSelectedSlotId(slotId);
    setActiveRoute(null);
    setNotice(null);
  }

  async function continueAfterLocationConfirmation(nodeId: FloorScopedId) {
    setAgentCurrentLocationId(null);
    setActiveRoute(null);
    const deferredPreference = deferredPreferenceRef.current;
    deferredPreferenceRef.current = null;
    if (deferredFindVehicleRef.current) {
      deferredFindVehicleRef.current = false;
      await continueFindVehicleFromLocation(nodeId);
      return true;
    }
    if (deferredReservationRouteRef.current) {
      deferredReservationRouteRef.current = false;
      await continueRouteToActiveReservationFromLocation(nodeId);
      return true;
    }
    if (!deferredPreference) return false;
    try {
      const result = await api.recommend({
        user_id: identity.userId,
        start_node_id: nodeId,
        charging_required: deferredPreference === "EV",
        accessible_required: deferredPreference === "ACCESSIBLE",
        near_elevator: deferredPreference === "NEAR_ELEVATOR",
        limit: 3,
      });
      setCandidates(result.recommendations);
      setRecommendedSlotIds(result.recommendations.map((candidate) => candidate.slot_id));
      setSelectedSlotId(null);
      appendAgentMessage(
        result.recommendations.length > 0
          ? "Tôi đã tìm thấy các ô phù hợp. Hãy chọn một ô."
          : noRecommendationMessage(deferredPreference),
        slotSelectionActions(result.recommendations),
      );
    } catch (error) {
      setNotice(vietnameseError(error));
    }
    return true;
  }

  async function confirmLocation(nodeId: FloorScopedId) {
    setPending("location");
    setNotice(null);
    try {
      const location = await api.confirmLocation({ user_id: identity.userId, node_id: nodeId });
      data.applyCurrentLocation?.(location);
      setNotice(`Đã cập nhật vị trí trong bãi: ${formatParkingLocation(location.node_id)}.`);
      await continueAfterLocationConfirmation(nodeId);
      return true;
    } catch (error) {
      await handleMutationFailure(error);
      return false;
    } finally {
      setPending(null);
    }
  }

  async function requestRecommendations(preferences: {
    chargingRequired: boolean;
    accessibleRequired: boolean;
    nearElevator: boolean;
  }): Promise<boolean> {
    const startNodeId = data.currentLocation?.node_id;
    if (!startNodeId) {
      setNotice("Hãy xác nhận vị trí hiện tại trước khi yêu cầu đề xuất.");
      return false;
    }
    setPending("recommend");
    setNotice(null);
    try {
      const result = await api.recommend({
        user_id: identity.userId,
        start_node_id: startNodeId,
        charging_required: preferences.chargingRequired,
        accessible_required: preferences.accessibleRequired,
        near_elevator: preferences.nearElevator,
        limit: 3,
      });
      setCandidates(result.recommendations);
      setRecommendedSlotIds(
        result.recommendations.map((candidate) => candidate.slot_id),
      );
      // Recommendation is read-only. The user must choose a candidate before
      // reservation, and no slot status is changed locally.
      setSelectedSlotId(null);
      setActiveRoute(null);
      appendAgentMessage(
        result.recommendations.length > 0
          ? "Tôi đã tìm thấy các ô phù hợp. Hãy chọn một ô."
          : noRecommendationMessage(
              preferences.chargingRequired
                ? "EV"
                : preferences.accessibleRequired
                  ? "ACCESSIBLE"
                  : preferences.nearElevator
                    ? "NEAR_ELEVATOR"
                    : "ANY",
            ),
        slotSelectionActions(result.recommendations),
      );
      return true;
    } catch (error) {
      setNotice(vietnameseError(error));
      return false;
    } finally {
      setPending(null);
    }
  }

  async function reserveSelected() {
    if (!identity.vehicleId) {
      setNotice("Tài khoản chưa có xe mặc định. Hãy thêm xe trước khi giữ chỗ.");
      return;
    }

    const slot = data.slots.find((candidate) => candidate.id === selectedSlotId);
    if (!slot) {
      setNotice("Hãy chọn một ô trên bản đồ trước khi giữ chỗ.");
      return;
    }
    if (slot.status !== "AVAILABLE") {
      setNotice(`Ô ${slot.id} hiện không trống. Hãy chọn một ô đang trống khác.`);
      return;
    }

    const request = {
      user_id: identity.userId,
      vehicle_id: identity.vehicleId,
      slot_id: slot.id,
      expected_version: slot.version,
    };
    const idempotencyKey = getOrCreateIdempotencyKey(
      reservationIdempotencyRef,
      JSON.stringify(request),
    );

    setPending("reserve");
    setNotice(null);
    clearRecommendations();
    try {
      await api.createReservation(request, undefined, idempotencyKey);
      clearIdempotencyKey(reservationIdempotencyRef);
      await data.refresh();
    } catch (error) {
      if (isDefinitiveMutationRejection(error)) {
        clearIdempotencyKey(reservationIdempotencyRef);
      }
      await handleMutationFailure(error);
    } finally {
      setPending(null);
    }
  }

  async function reserveSelectedAndRoute(slotId = selectedSlotId ?? undefined): Promise<boolean> {
    if (reserveAndRouteInFlightRef.current) return false;
    if (!identity.vehicleId) {
      setNotice("Tài khoản chưa có xe mặc định. Hãy thêm xe trước khi giữ chỗ.");
      return false;
    }

    const slot = data.slots.find((candidate) => candidate.id === slotId);
    const startNodeId = data.currentLocation?.node_id;
    if (!slot || !startNodeId) {
      setNotice("Hãy xác nhận vị trí và chọn một ô đang trống trước.");
      return false;
    }
    if (slot.status !== "AVAILABLE") {
      setSelectedSlotId(null);
      setNotice(`Ô ${slot.id} vừa hết chỗ. Hãy chọn một ô đang trống khác.`);
      return false;
    }

    const reservationRequest = {
      user_id: identity.userId,
      vehicle_id: identity.vehicleId,
      slot_id: slot.id,
      expected_version: slot.version,
    };
    const idempotencyKey = getOrCreateIdempotencyKey(
      reservationIdempotencyRef,
      JSON.stringify(reservationRequest),
    );

    reserveAndRouteInFlightRef.current = true;
    setPending("reserve-and-route");
    setNotice(null);
    let reservationCreated = false;
    try {
      await api.createReservation(
        reservationRequest,
        undefined,
        idempotencyKey,
      );
      clearIdempotencyKey(reservationIdempotencyRef);
      reservationCreated = true;

      const snapshot = await data.refresh();
      clearRecommendations();
      setSelectedSlotId(slot.id);
      const route = await api.getRoute({
        start_node_id: snapshot.currentLocation?.node_id ?? startNodeId,
        destination_node_id: slot.id,
        mode: "VEHICLE",
      });
      setActiveRoute(route);
      setNotice(`Đã giữ ô ${slot.id} và tải chỉ đường.`);
      return true;
    } catch (error) {
      if (!reservationCreated && isDefinitiveMutationRejection(error)) {
        clearIdempotencyKey(reservationIdempotencyRef);
      }
      if (reservationCreated) {
        setNotice(`Đã giữ ô ${slot.id}, nhưng chưa tải được chỉ đường. Bạn có thể thử lại.`);
      } else {
        await handleMutationFailure(error);
      }
      return reservationCreated;
    } finally {
      reserveAndRouteInFlightRef.current = false;
      setPending(null);
    }
  }

  async function cancelActiveReservation(): Promise<boolean> {
    const reservation = data.activeReservation;
    if (!reservation) {
      setNotice("Bạn không có chỗ đang giữ để hủy.");
      return false;
    }
    setPending("cancel-reservation");
    setNotice(null);
    try {
      await api.cancelReservation(reservation.id, identity.userId);
      await data.refresh();
      setSelectedSlotId(null);
      setActiveRoute(null);
      clearRecommendations();
      return true;
    } catch (error) {
      await handleMutationFailure(error);
      return false;
    } finally {
      setPending(null);
    }
  }

  async function requestRouteToSelected() {
    const startNodeId = data.currentLocation?.node_id;
    if (!startNodeId || !selectedSlotId) {
      setNotice("Hãy xác nhận vị trí và chọn ô đích trước khi yêu cầu chỉ đường.");
      return;
    }
    setPending("route");
    setNotice(null);
    clearRecommendations();
    try {
      const route = await api.getRoute({
        start_node_id: startNodeId,
        destination_node_id: selectedSlotId,
        mode: "VEHICLE",
      });
      setActiveRoute(route);
    } catch (error) {
      setNotice(vietnameseError(error));
    } finally {
      setPending(null);
    }
  }

  async function continueRouteToActiveReservationFromLocation(
    startNodeId: FloorScopedId,
  ): Promise<boolean> {
    const reservation = data.activeReservation;
    if (!reservation) {
      setNotice("Bạn không có chỗ đang giữ để chỉ đường.");
      return false;
    }
    setPending("route");
    setNotice(null);
    try {
      const route = await api.getRoute({
        start_node_id: startNodeId,
        destination_node_id: reservation.slot_id,
        mode: "VEHICLE",
      });
      setActiveRoute(route);
      return true;
    } catch (error) {
      setNotice(
        formatApiErrorForOperator(
          error,
          "Chưa tải được chỉ đường tới ô đã giữ. Bạn có thể thử lại.",
        ),
      );
      return false;
    } finally {
      setPending(null);
    }
  }

  async function requestRouteToActiveReservation(): Promise<boolean> {
    const reservation = data.activeReservation;
    const startNodeId = data.currentLocation?.node_id;
    if (!reservation) {
      setNotice("Bạn không có chỗ đang giữ để chỉ đường.");
      return false;
    }
    if (!startNodeId) {
      deferredReservationRouteRef.current = true;
      setRequestedPanel({ kind: "location" });
      setNotice("Hãy xác nhận vị trí hiện tại trước khi chỉ đường tới ô đã giữ.");
      return false;
    }
    return continueRouteToActiveReservationFromLocation(startNodeId);
  }

  async function confirmParking(): Promise<boolean> {
    if (!identity.vehicleId) {
      setNotice("Tài khoản chưa có xe mặc định. Hãy thêm xe trước khi xác nhận đỗ.");
      return false;
    }

    const reservation = data.activeReservation;
    const initialSlot = data.slots.find(
      (candidate) => candidate.id === reservation?.slot_id,
    );
    if (!reservation || !initialSlot) {
      setNotice("Bạn chưa có chỗ đỗ đã giữ để xác nhận.");
      return false;
    }

    const request = {
      user_id: identity.userId,
      vehicle_id: identity.vehicleId,
      reservation_id: reservation.id,
      expected_version: initialSlot.version,
    };
    const idempotencyKey = getOrCreateIdempotencyKey(
      confirmParkingIdempotencyRef,
      JSON.stringify(request),
    );

    setPending("confirm-parking");
    setNotice(null);
    clearRecommendations();
    try {
      await api.confirmParking(request, undefined, idempotencyKey);
      clearIdempotencyKey(confirmParkingIdempotencyRef);
      await data.refresh();
      setActiveRoute(null);
      setSelectedSlotId(null);
      setNotice(`Đã xác nhận đỗ xe tại ${formatParkingLocation(reservation.slot_id)}.`);
      return true;
    } catch (error) {
      if (isDefinitiveMutationRejection(error)) {
        clearIdempotencyKey(confirmParkingIdempotencyRef);
      }
      await handleMutationFailure(error);
      return false;
    } finally {
      setPending(null);
    }
  }

  async function continueFindVehicleFromLocation(startNodeId: FloorScopedId) {
    setPending("find-car");
    setNotice(null);
    clearRecommendations();
    try {
      const session = await api.getActiveSession(identity.userId);
      if (!session) {
        setNotice("Bạn chưa có phiên đỗ xe đang hoạt động.");
        return;
      }
      const route = await api.getRoute({
        start_node_id: startNodeId,
        destination_node_id: session.slot_id,
        mode: "PEDESTRIAN",
      });
      await data.refresh();
      setActiveRoute(route);
    } catch (error) {
      setNotice(vietnameseError(error));
    } finally {
      setPending(null);
    }
  }

  async function findVehicleAndRoute() {
    if (!data.activeSession) {
      setNotice("Bạn chưa có phiên đỗ xe đang hoạt động.");
      return;
    }
    deferredFindVehicleRef.current = true;
    setRequestedPanel({ kind: "location", purpose: "find-vehicle" });
    setNotice("Chọn vị trí hiện tại để ParkSmart chỉ đường tới xe của bạn.");
  }

  async function completeSession(): Promise<boolean> {
    const session = data.activeSession;
    const slot = data.slots.find((candidate) => candidate.id === session?.slot_id);
    if (!session || !slot) {
      setNotice("Không có phiên đỗ xe đang hoạt động để kết thúc.");
      return false;
    }

    const request = {
      user_id: identity.userId,
      expected_version: slot.version,
    };
    const idempotencyKey = getOrCreateIdempotencyKey(
      completeSessionIdempotencyRef,
      JSON.stringify({ session_id: session.session_id, ...request }),
    );

    setPending("complete-session");
    setNotice(null);
    clearRecommendations();
    try {
      const completion = await api.completeSession(
        session.session_id,
        request,
        undefined,
        idempotencyKey,
      );
      clearIdempotencyKey(completeSessionIdempotencyRef);
      setSelectedSlotId(null);
      setActiveRoute(null);
      setNotice(completionNotice(completion));
      try {
        await data.refresh();
      } catch {
        // The completion response is the mutation success boundary.  A later
        // snapshot failure must never present this completed session as failed.
        setNotice(completionNotice(completion, true));
      }
      return true;
    } catch (error) {
      if (isDefinitiveMutationRejection(error)) {
        clearIdempotencyKey(completeSessionIdempotencyRef);
      }
      await handleMutationFailure(error);
      return false;
    } finally {
      setPending(null);
    }
  }

  async function resetDemo() {
    setPending("reset");
    setNotice(null);
    try {
      await api.resetDemo();
      clearIdempotencyKey(reservationIdempotencyRef);
      clearIdempotencyKey(confirmParkingIdempotencyRef);
      clearIdempotencyKey(completeSessionIdempotencyRef);
      await data.refresh();
      clearRecommendations();
      setSelectedSlotId(null);
      setActiveRoute(null);
      setMessages([welcomeMessage()]);
      setAgentCurrentLocationId(null);
      setLastToolNames([]);
      setRetryMessage(null);
      setThreadId(rotateThreadId(identity.userId));
    } catch (error) {
      await handleMutationFailure(error);
    } finally {
      setPending(null);
    }
  }

  async function sendAgentMessageInternal(
    message: string,
    {
      appendUserMessage = true,
      currentLocationOverride,
    }: {
      appendUserMessage?: boolean;
      currentLocationOverride?: FloorScopedId;
    } = {},
  ) {
    if (!isAgentEnabled()) return null;
    const trimmed = message.trim();
    if (!trimmed || !threadId || chatInFlightRef.current) return null;
    chatInFlightRef.current = true;
    if (appendUserMessage) {
      setMessages((current) => [
        ...current,
        {
          id: nextMessageId("user"),
          role: "user",
          text: trimmed,
          uiActions: [],
          consumedActionIds: [],
        },
      ]);
    }
    setPending("chat");
    setNotice(null);
    setRetryMessage(null);
    try {
      const response = await api.chat({
        thread_id: threadId,
        user_id: identity.userId,
        vehicle_id: identity.vehicleId,
        current_location: currentLocationOverride ?? data.currentLocation?.node_id ?? null,
        message: trimmed,
      });
      if (
        response.tool_names.some((toolName) =>
          AUTHORITATIVE_REFRESH_TOOLS.has(toolName),
        )
      ) {
        await refreshQuietly();
      }
      setMessages((current) => [
        ...current,
        {
          id: nextMessageId("agent"),
          role: "agent",
          text: response.message,
          uiActions: response.ui_actions ?? [],
          consumedActionIds: [],
        },
      ]);
      setCandidates([]);
      if (response.tool_names.includes("recommend_parking_slot")) {
        setRecommendedSlotIds(response.recommended_slot_ids);
      } else {
        clearRecommendations();
      }
      setSelectedSlotId(response.selected_slot);
      setActiveRoute(response.route);
      setAgentCurrentLocationId(response.current_location);
      setLastToolNames(response.tool_names);
      return response.message;
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.status === 429 &&
        error.code === "AGENT_DAILY_LIMIT_REACHED"
      ) {
        setNotice(
          "Bạn đã dùng hết lượt trợ lý AI hôm nay. Bạn vẫn có thể tìm chỗ, giữ chỗ và báo sự cố bằng các thao tác có sẵn. Vui lòng thử lại vào ngày mai.",
        );
      } else if (
        error instanceof ApiError &&
        error.status === 503 &&
        error.code === "AGENT_TOOL_UNAVAILABLE"
      ) {
        setNotice(
          formatApiErrorForOperator(
            error,
            "Trợ lý ParkSmart đang tạm thời không khả dụng. Bạn có thể thử gửi lại yêu cầu này.",
          ),
        );
        setRetryMessage(trimmed);
      } else {
        setNotice(vietnameseError(error));
      }
      return null;
    } finally {
      chatInFlightRef.current = false;
      setPending(null);
    }
  }

  async function retryAgentMessage() {
    if (!retryMessage) return;
    await sendAgentMessageInternal(retryMessage, { appendUserMessage: false });
  }

  async function sendAgentMessage(message: string) {
    return sendAgentMessageInternal(message);
  }

  async function updateAdjacentSlotStatus(
    slotId: FloorScopedId,
    status: AdjacentSlotObservedStatus,
    evidence?: File | null,
  ) {
    if (adjacentObservationInFlightRef.current) return null;
    const slot = data.slots.find((candidate) => candidate.id === slotId);
    if (!data.activeSession || !slot) {
      setNotice("Chỉ có thể cập nhật ô bên cạnh sau khi bạn đã xác nhận đỗ xe.");
      return null;
    }
    adjacentObservationInFlightRef.current = true;
    setPending("observe-adjacent-slot");
    setPendingAdjacentSlotId(slot.id);
    setNotice(null);
    try {
      const observation = await api.observeAdjacentSlot(slot.id, {
        user_id: identity.userId,
        observed_status: status,
        expected_slot_version: slot.version,
        evidence,
      });
      await data.refresh();
      return observation;
    } catch (error) {
      await refreshQuietly();
      setNotice(
        formatApiErrorForOperator(
          error,
          "Không thể cập nhật ô bên cạnh. Trạng thái mới nhất đã được tải lại.",
        ),
      );
      return null;
    } finally {
      adjacentObservationInFlightRef.current = false;
      setPendingAdjacentSlotId(null);
      setPending(null);
    }
  }

  function consumeAction(messageId: string, actionId: string) {
    setMessages((current) =>
      current.map((message) =>
        message.id === messageId && !message.consumedActionIds.includes(actionId)
          ? {
              ...message,
              consumedActionIds: [...message.consumedActionIds, actionId],
            }
          : message,
      ),
    );
  }

  async function executeUiAction(messageId: string, action: ChatUiAction) {
    const actionKey = `${messageId}:${action.id}`;
    const sourceMessage = messages.find((message) => message.id === messageId);
    const attachedAction = sourceMessage?.uiActions.find(
      (candidate) => candidate.id === action.id,
    );
    if (
      !sourceMessage ||
      !attachedAction ||
      sourceMessage.consumedActionIds.includes(action.id) ||
      actionInFlightRef.current.has(actionKey)
    ) {
      return;
    }

    actionInFlightRef.current.add(actionKey);
    try {
      if (!KNOWN_UI_ACTION_TYPES.has(attachedAction.type)) {
        setNotice("Thao tác này chưa được hỗ trợ và đã được bỏ qua an toàn.");
        return;
      }
      let completed = false;
      switch (attachedAction.type) {
        case "SELECT_LOCATION":
          setRequestedPanel({ kind: "location" });
          completed = true;
          break;
        case "SELECT_PARKING_PREFERENCE": {
          const preference = attachedAction.payload.preference;
          if (!preferenceIsAvailable(preference)) {
            setNotice("Tính năng tìm ô dễ tiếp cận hiện chưa khả dụng tại bãi này.");
            break;
          }
          if (!data.currentLocation?.node_id) {
            deferredPreferenceRef.current = preference;
            setRequestedPanel({ kind: "location" });
            completed = true;
          } else {
            completed = await requestRecommendations(preferencesFor(preference));
          }
          break;
        }
        case "SELECT_SLOT": {
          const slotId = attachedAction.payload.slot_id;
          if (!data.slots.some((slot) => slot.id === slotId)) {
            setNotice("Ô được chọn không còn trong dữ liệu hiện tại.");
            break;
          }
          selectCandidate(slotId);
          appendAgentMessage(`Bạn đã chọn ${slotId}.`, [
            {
              id: `reserve-and-route:${slotId.toLowerCase()}`,
              type: "RESERVE_AND_ROUTE",
              label: "Giữ ô và chỉ đường",
              payload: { slot_id: slotId },
              style: "primary",
              requires_confirmation: true,
            },
          ]);
          completed = true;
          break;
        }
        case "RESERVE_AND_ROUTE":
          completed = await reserveSelectedAndRoute(attachedAction.payload.slot_id);
          break;
        case "CONFIRM_PARKING":
          completed = await confirmParking();
          break;
        case "FIND_VEHICLE":
          await findVehicleAndRoute();
          break;
        case "COMPLETE_SESSION":
          completed = await completeSession();
          break;
        case "OPEN_WRONG_PARKING_REPORT":
          setRequestedPanel({
            kind: "wrong-parking-report",
            slotId: attachedAction.payload.slot_id ?? selectedSlotId,
          });
          completed = true;
          break;
        case "CANCEL":
          completed = await cancelActiveReservation();
          break;
      }
      if (completed && !REPEATABLE_UI_ACTION_TYPES.has(attachedAction.type)) {
        consumeAction(messageId, action.id);
      }
    } finally {
      actionInFlightRef.current.delete(actionKey);
    }
  }

  return {
    candidates,
    recommendedSlotIds,
    selectedSlotId,
    activeRoute,
    currentLocationId: agentCurrentLocationId ?? data.currentLocation?.node_id ?? null,
    lastToolNames,
    messages,
    threadId,
    pending,
    pendingAdjacentSlotId,
    notice,
    retryMessage,
    requestedPanel,
    selectCandidate,
    clearRoute: () => setActiveRoute(null),
    confirmLocation,
    requestRecommendations,
    reserveSelected,
    reserveSelectedAndRoute,
    cancelActiveReservation,
    requestRouteToSelected,
    requestRouteToActiveReservation,
    confirmParking,
    findVehicleAndRoute,
    completeSession,
    updateAdjacentSlotStatus,
    resetDemo,
    sendAgentMessage,
    retryAgentMessage,
    executeUiAction,
    clearRequestedPanel: () => {
      deferredFindVehicleRef.current = false;
      deferredReservationRouteRef.current = false;
      deferredPreferenceRef.current = null;
      setRequestedPanel(null);
    },
  };
}
