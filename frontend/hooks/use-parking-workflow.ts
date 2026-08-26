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
  getOrCreateThreadId,
  MVP_DEMO_PARKING_IDENTITY,
  rotateThreadId,
} from "@/lib/demo";
import type { ParkingIdentity } from "@/lib/auth";
import { isAgentEnabled } from "@/lib/public-config";
import type {
  ChatUiAction,
  AdjacentSlotObservedStatus,
  FloorId,
  FloorScopedId,
  ParkingPreference,
  RecommendationCandidate,
  RouteResult,
  SlotObservation,
} from "@/lib/types";

export type WorkflowAction =
  | "location"
  | "qr-location"
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
  | { kind: "location" }
  | { kind: "qr-location" }
  | { kind: "wrong-parking-report"; slotId: FloorScopedId | null };

type WorkflowApi = Pick<
  ParkSmartApiClient,
  | "confirmLocation"
  | "scanLocation"
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
  scanLocationQr: (qrPayload: string) => Promise<boolean>;
  requestRecommendations: (preferences: {
    chargingRequired: boolean;
    accessibleRequired: boolean;
    nearElevator: boolean;
  }) => Promise<void>;
  reserveSelected: () => Promise<void>;
  reserveSelectedAndRoute: (slotId?: FloorScopedId) => Promise<void>;
  cancelActiveReservation: () => Promise<void>;
  requestRouteToSelected: () => Promise<void>;
  confirmParking: () => Promise<void>;
  findVehicleAndRoute: () => Promise<void>;
  completeSession: () => Promise<void>;
  updateAdjacentSlotStatus: (
    slotId: FloorScopedId,
    status: AdjacentSlotObservedStatus,
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
  "SCAN_LOCATION_QR",
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
  "SCAN_LOCATION_QR",
  "SELECT_LOCATION",
  "SELECT_PARKING_PREFERENCE",
  "SELECT_SLOT",
  "FIND_VEHICLE",
  "OPEN_WRONG_PARKING_REPORT",
]);

const WELCOME_ACTIONS: ChatUiAction[] = [
  {
    id: "welcome-scan-location",
    type: "SCAN_LOCATION_QR",
    label: "Quét QR vị trí",
    payload: {},
    style: "secondary",
    requires_confirmation: false,
  },
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

function floorIdFromNode(nodeId: FloorScopedId): FloorId | undefined {
  const floorId = nodeId.slice(0, 2);
  return floorId === "F1" || floorId === "F2" || floorId === "F3"
    ? floorId
    : undefined;
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
  const resumeAgentAfterLocationRef = useRef(false);
  const scanInFlightRef = useRef(false);
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
      label: `Chọn ${candidate.slot_id.replace("F1-", "ô ")}`,
      payload: { slot_id: candidate.slot_id },
      style: "primary" as const,
      requires_confirmation: false,
    }));
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
    if (!deferredPreference) return false;
    try {
      const result = await api.recommend({
        user_id: identity.userId,
        start_node_id: nodeId,
        floor_id: floorIdFromNode(nodeId),
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
          : "Hiện chưa có ô phù hợp với nhu cầu này.",
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
      await continueAfterLocationConfirmation(nodeId);
      setAgentCurrentLocationId(null);
      setActiveRoute(null);
      const deferredPreference = deferredPreferenceRef.current;
      deferredPreferenceRef.current = null;
      if (deferredPreference) {
        try {
          const result = await api.recommend({
            user_id: identity.userId,
            start_node_id: nodeId,
            floor_id: floorIdFromNode(nodeId),
            charging_required: deferredPreference === "EV",
            accessible_required: deferredPreference === "ACCESSIBLE",
            near_elevator: deferredPreference === "NEAR_ELEVATOR",
            limit: 3,
          });
          setCandidates(result.recommendations);
          setRecommendedSlotIds(
            result.recommendations.map((candidate) => candidate.slot_id),
          );
          setSelectedSlotId(null);
          appendAgentMessage(
            result.recommendations.length > 0
              ? "Tôi đã tìm thấy các ô phù hợp. Hãy chọn một ô."
              : "Hiện chưa có ô phù hợp với nhu cầu này.",
            slotSelectionActions(result.recommendations),
          );
        } catch (error) {
          setNotice(vietnameseError(error));
        }
      }
      return true;
    } catch (error) {
      await handleMutationFailure(error);
      return false;
    } finally {
      setPending(null);
    }
  }

  async function scanLocationQr(qrPayload: string) {
    if (scanInFlightRef.current) return false;
    scanInFlightRef.current = true;
    setPending("qr-location");
    setNotice(null);
    try {
      const scanned = await api.scanLocation({
        user_id: identity.userId,
        qr_payload: qrPayload,
      });
      data.applyCurrentLocation?.({ user_id: scanned.user_id, node_id: scanned.node_id });
      const continuedDeterministically = await continueAfterLocationConfirmation(
        scanned.node_id,
      );
      const shouldResumeAgent =
        !continuedDeterministically && resumeAgentAfterLocationRef.current;
      resumeAgentAfterLocationRef.current = false;
      setRequestedPanel(null);
      setNotice(`Đã xác định: ${scanned.label}`);
      if (shouldResumeAgent) {
        await sendAgentMessageInternal(
          "Vị trí đã được xác nhận bằng QR. Hãy tiếp tục yêu cầu trước đó.",
          { appendUserMessage: false, currentLocationOverride: scanned.node_id },
        );
      }
      return true;
    } catch (error) {
      setNotice(vietnameseError(error));
      return false;
    } finally {
      scanInFlightRef.current = false;
      setPending(null);
    }
  }

  async function requestRecommendations(preferences: {
    chargingRequired: boolean;
    accessibleRequired: boolean;
    nearElevator: boolean;
  }) {
    const startNodeId = data.currentLocation?.node_id;
    if (!startNodeId) {
      setNotice("Hãy xác nhận vị trí hiện tại trước khi yêu cầu đề xuất.");
      return;
    }
    setPending("recommend");
    setNotice(null);
    try {
      const result = await api.recommend({
        user_id: identity.userId,
        start_node_id: startNodeId,
        floor_id: floorIdFromNode(startNodeId),
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
          : "Hiện chưa có ô phù hợp với nhu cầu này.",
        slotSelectionActions(result.recommendations),
      );
    } catch (error) {
      setNotice(vietnameseError(error));
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
    setPending("reserve");
    setNotice(null);
    clearRecommendations();
    try {
      await api.createReservation({
        user_id: identity.userId,
        vehicle_id: identity.vehicleId,
        slot_id: slot.id,
        expected_version: slot.version,
      });
      await data.refresh();
    } catch (error) {
      await handleMutationFailure(error);
    } finally {
      setPending(null);
    }
  }

  async function reserveSelectedAndRoute(slotId = selectedSlotId ?? undefined) {
    if (reserveAndRouteInFlightRef.current) return;
    if (!identity.vehicleId) {
      setNotice("Tài khoản chưa có xe mặc định. Hãy thêm xe trước khi giữ chỗ.");
      return;
    }
    const slot = data.slots.find((candidate) => candidate.id === slotId);
    const startNodeId = data.currentLocation?.node_id;
    if (!slot || !startNodeId) {
      setNotice("Hãy xác nhận vị trí và chọn một ô đang trống trước.");
      return;
    }
    if (slot.status !== "AVAILABLE") {
      setSelectedSlotId(null);
      setNotice(`Ô ${slot.id} vừa hết chỗ. Hãy chọn một ô đang trống khác.`);
      return;
    }

    reserveAndRouteInFlightRef.current = true;
    setPending("reserve-and-route");
    setNotice(null);
    let reservationCreated = false;
    try {
      await api.createReservation({
        user_id: identity.userId,
        vehicle_id: identity.vehicleId,
        slot_id: slot.id,
        expected_version: slot.version,
      });
      reservationCreated = true;
      const snapshot = await data.refresh();
      clearRecommendations();
      setSelectedSlotId(slot.id);
      const route = await api.getRoute({
        start_node_id: snapshot.currentLocation?.node_id ?? startNodeId,
        destination_node_id: slot.id,
      });
      setActiveRoute(route);
      setNotice(`Đã giữ ô ${slot.id} và tải chỉ đường.`);
    } catch (error) {
      if (reservationCreated) {
        setNotice(
          formatApiErrorForOperator(
            error,
            `Đã giữ ô ${slot.id}, nhưng chưa tải được chỉ đường. Bạn có thể thử lại.`,
          ),
        );
      } else {
        await handleMutationFailure(error);
      }
    } finally {
      reserveAndRouteInFlightRef.current = false;
      setPending(null);
    }
  }

  async function cancelActiveReservation() {
    const reservation = data.activeReservation;
    if (!reservation) {
      setNotice("Bạn không có chỗ đang giữ để hủy.");
      return;
    }
    setPending("cancel-reservation");
    setNotice(null);
    try {
      await api.cancelReservation(reservation.id, identity.userId);
      await data.refresh();
      setSelectedSlotId(null);
      setActiveRoute(null);
      clearRecommendations();
    } catch (error) {
      await handleMutationFailure(error);
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
      });
      setActiveRoute(route);
    } catch (error) {
      setNotice(vietnameseError(error));
    } finally {
      setPending(null);
    }
  }

  async function confirmParking() {
    if (!identity.vehicleId) {
      setNotice("Tài khoản chưa có xe mặc định. Hãy thêm xe trước khi xác nhận đỗ.");
      return;
    }
    const reservation = data.activeReservation;
    const initialSlot = data.slots.find(
      (candidate) => candidate.id === reservation?.slot_id,
    );
    if (!reservation || !initialSlot) {
      setNotice("Bạn chưa có chỗ đỗ đã giữ để xác nhận.");
      return;
    }
    setPending("confirm-parking");
    setNotice(null);
    clearRecommendations();
    try {
      let authoritativeSlot = initialSlot;
      if (data.currentLocation?.node_id !== reservation.slot_id) {
        await api.confirmLocation({
          user_id: identity.userId,
          node_id: reservation.slot_id,
        });
        const arrivalSnapshot = await data.refresh();
        authoritativeSlot =
          arrivalSnapshot.slots.find(
            (candidate) => candidate.id === reservation.slot_id,
          ) ?? initialSlot;
        setAgentCurrentLocationId(null);
      }
      await api.confirmParking({
        user_id: identity.userId,
        vehicle_id: identity.vehicleId,
        reservation_id: reservation.id,
        expected_version: authoritativeSlot.version,
      });
      await data.refresh();
      setActiveRoute(null);
      setNotice(`Đã xác nhận bạn đến ${reservation.slot_id} và hoàn tất đỗ xe.`);
    } catch (error) {
      await handleMutationFailure(error);
    } finally {
      setPending(null);
    }
  }

  async function findVehicleAndRoute() {
    const startNodeId = data.currentLocation?.node_id;
    if (!startNodeId) {
      setNotice("Hãy xác nhận vị trí hiện tại trước khi tìm xe.");
      return;
    }
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
        destination_node_id: session.destination_node_id || session.slot_id,
      });
      await data.refresh();
      setSelectedSlotId(session.slot_id);
      setActiveRoute(route);
    } catch (error) {
      setNotice(vietnameseError(error));
    } finally {
      setPending(null);
    }
  }

  async function completeSession() {
    const session = data.activeSession;
    const slot = data.slots.find((candidate) => candidate.id === session?.slot_id);
    if (!session || !slot) {
      setNotice("Không có phiên đỗ xe đang hoạt động để kết thúc.");
      return;
    }
    setPending("complete-session");
    setNotice(null);
    clearRecommendations();
    try {
      await api.completeSession(session.session_id, {
        user_id: identity.userId,
        expected_version: slot.version,
      });
      await data.refresh();
      setSelectedSlotId(null);
      setActiveRoute(null);
    } catch (error) {
      await handleMutationFailure(error);
    } finally {
      setPending(null);
    }
  }

  async function resetDemo() {
    setPending("reset");
    setNotice(null);
    try {
      await api.resetDemo();
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
    if (!REPEATABLE_UI_ACTION_TYPES.has(attachedAction.type)) {
      consumeAction(messageId, action.id);
    }
    try {
      if (!KNOWN_UI_ACTION_TYPES.has(attachedAction.type)) {
        setNotice("Thao tác này chưa được hỗ trợ và đã được bỏ qua an toàn.");
        return;
      }
      switch (attachedAction.type) {
        case "SCAN_LOCATION_QR":
          resumeAgentAfterLocationRef.current = sourceMessage.id !== "welcome";
          setRequestedPanel({ kind: "qr-location" });
          break;
        case "SELECT_LOCATION":
          setRequestedPanel({ kind: "location" });
          break;
        case "SELECT_PARKING_PREFERENCE": {
          const preference = attachedAction.payload.preference;
          if (!data.currentLocation?.node_id) {
            deferredPreferenceRef.current = preference;
            resumeAgentAfterLocationRef.current = false;
            setRequestedPanel({ kind: "qr-location" });
          } else {
            await requestRecommendations(preferencesFor(preference));
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
          break;
        }
        case "RESERVE_AND_ROUTE":
          await reserveSelectedAndRoute(attachedAction.payload.slot_id);
          break;
        case "CONFIRM_PARKING":
          await confirmParking();
          break;
        case "FIND_VEHICLE":
          await findVehicleAndRoute();
          break;
        case "COMPLETE_SESSION":
          await completeSession();
          break;
        case "OPEN_WRONG_PARKING_REPORT":
          setRequestedPanel({
            kind: "wrong-parking-report",
            slotId: attachedAction.payload.slot_id ?? selectedSlotId,
          });
          break;
        case "CANCEL":
          await cancelActiveReservation();
          break;
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
    scanLocationQr,
    requestRecommendations,
    reserveSelected,
    reserveSelectedAndRoute,
    cancelActiveReservation,
    requestRouteToSelected,
    confirmParking,
    findVehicleAndRoute,
    completeSession,
    updateAdjacentSlotStatus,
    resetDemo,
    sendAgentMessage,
    retryAgentMessage,
    executeUiAction,
    clearRequestedPanel: () => setRequestedPanel(null),
  };
}
