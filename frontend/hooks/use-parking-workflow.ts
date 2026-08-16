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
  getOrCreateDemoThreadId,
  MVP_DEMO_USER_ID,
  MVP_DEMO_VEHICLE_ID,
  rotateDemoThreadId,
} from "@/lib/demo";
import type {
  FloorScopedId,
  RecommendationCandidate,
  RouteResult,
} from "@/lib/types";

export type WorkflowAction =
  | "location"
  | "recommend"
  | "reserve"
  | "route"
  | "confirm-parking"
  | "find-car"
  | "complete-session"
  | "reset"
  | "chat";

export type WorkflowMessage = { role: "agent" | "user"; text: string };

type WorkflowApi = Pick<
  ParkSmartApiClient,
  | "confirmLocation"
  | "recommend"
  | "createReservation"
  | "getRoute"
  | "confirmParking"
  | "getActiveSession"
  | "completeSession"
  | "resetDemo"
  | "chat"
>;

export interface WorkflowData
  extends Pick<
    ParkSmartData,
    "slots" | "currentLocation" | "activeReservation" | "activeSession"
  > {
  refresh: () => Promise<ParkSmartSnapshot>;
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
  notice: string | null;
  retryMessage: string | null;
  selectCandidate: (slotId: FloorScopedId) => void;
  clearRoute: () => void;
  confirmLocation: (nodeId: FloorScopedId) => Promise<boolean>;
  requestRecommendations: (preferences: {
    chargingRequired: boolean;
    accessibleRequired: boolean;
    nearElevator: boolean;
  }) => Promise<void>;
  reserveSelected: () => Promise<void>;
  requestRouteToSelected: () => Promise<void>;
  confirmParking: () => Promise<void>;
  findVehicleAndRoute: () => Promise<void>;
  completeSession: () => Promise<void>;
  resetDemo: () => Promise<void>;
  sendAgentMessage: (message: string) => Promise<string | null>;
  retryAgentMessage: () => Promise<void>;
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

export function useParkingWorkflow(
  data: WorkflowData,
  api: WorkflowApi = parkSmartApi,
): ParkingWorkflow {
  const [candidates, setCandidates] = useState<RecommendationCandidate[]>([]);
  const [recommendedSlotIds, setRecommendedSlotIds] = useState<FloorScopedId[]>([]);
  const [selectedSlotId, setSelectedSlotId] = useState<FloorScopedId | null>(null);
  const [activeRoute, setActiveRoute] = useState<RouteResult | null>(null);
  const [agentCurrentLocationId, setAgentCurrentLocationId] =
    useState<FloorScopedId | null>(null);
  const [lastToolNames, setLastToolNames] = useState<string[]>([]);
  const [messages, setMessages] = useState<WorkflowMessage[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [pending, setPending] = useState<WorkflowAction | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [retryMessage, setRetryMessage] = useState<string | null>(null);
  const chatInFlightRef = useRef(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setThreadId(getOrCreateDemoThreadId());
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

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

  async function confirmLocation(nodeId: FloorScopedId) {
    setPending("location");
    setNotice(null);
    try {
      await api.confirmLocation({ user_id: MVP_DEMO_USER_ID, node_id: nodeId });
      await data.refresh();
      setAgentCurrentLocationId(null);
      setActiveRoute(null);
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
        user_id: MVP_DEMO_USER_ID,
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
    } catch (error) {
      setNotice(vietnameseError(error));
    } finally {
      setPending(null);
    }
  }

  async function reserveSelected() {
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
        user_id: MVP_DEMO_USER_ID,
        vehicle_id: MVP_DEMO_VEHICLE_ID,
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
    const reservation = data.activeReservation;
    const slot = data.slots.find((candidate) => candidate.id === reservation?.slot_id);
    if (!reservation || !slot) {
      setNotice("Bạn chưa có chỗ đỗ đã giữ để xác nhận.");
      return;
    }
    setPending("confirm-parking");
    setNotice(null);
    clearRecommendations();
    try {
      await api.confirmParking({
        user_id: MVP_DEMO_USER_ID,
        vehicle_id: MVP_DEMO_VEHICLE_ID,
        reservation_id: reservation.id,
        expected_version: slot.version,
      });
      await data.refresh();
      setActiveRoute(null);
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
      const session = await api.getActiveSession(MVP_DEMO_USER_ID);
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
        user_id: MVP_DEMO_USER_ID,
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
      setMessages([]);
      setAgentCurrentLocationId(null);
      setLastToolNames([]);
      setRetryMessage(null);
      setThreadId(rotateDemoThreadId());
    } catch (error) {
      await handleMutationFailure(error);
    } finally {
      setPending(null);
    }
  }

  async function sendAgentMessage(message: string, appendUserMessage = true) {
    const trimmed = message.trim();
    if (!trimmed || !threadId || chatInFlightRef.current) return null;
    chatInFlightRef.current = true;
    if (appendUserMessage) {
      setMessages((current) => [...current, { role: "user", text: trimmed }]);
    }
    setPending("chat");
    setNotice(null);
    setRetryMessage(null);
    try {
      const response = await api.chat({
        thread_id: threadId,
        user_id: MVP_DEMO_USER_ID,
        vehicle_id: MVP_DEMO_VEHICLE_ID,
        current_location: data.currentLocation?.node_id ?? null,
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
        { role: "agent", text: response.message },
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
    await sendAgentMessage(retryMessage, false);
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
    notice,
    retryMessage,
    selectCandidate,
    clearRoute: () => setActiveRoute(null),
    confirmLocation,
    requestRecommendations,
    reserveSelected,
    requestRouteToSelected,
    confirmParking,
    findVehicleAndRoute,
    completeSession,
    resetDemo,
    sendAgentMessage,
    retryAgentMessage,
  };
}
