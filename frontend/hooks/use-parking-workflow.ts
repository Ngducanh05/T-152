"use client";

import { useState } from "react";

import type { ParkSmartData, ParkSmartSnapshot } from "@/hooks/use-parksmart-data";
import { ApiError, parkSmartApi, type ParkSmartApiClient } from "@/lib/api";
import {
  createDemoThreadId,
  MVP_DEMO_USER_ID,
  MVP_DEMO_VEHICLE_ID,
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
  messages: WorkflowMessage[];
  threadId: string;
  pending: WorkflowAction | null;
  notice: string | null;
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
  sendAgentMessage: (message: string) => Promise<void>;
}

function vietnameseError(error: unknown) {
  return error instanceof ApiError
    ? `${error.code}: ${error.message}`
    : "Không thể kết nối tới ParkSmart API. Vui lòng thử lại.";
}

function isSlotConflict(error: unknown) {
  return error instanceof ApiError && error.code === "SLOT_NOT_AVAILABLE";
}

export function useParkingWorkflow(
  data: WorkflowData,
  api: WorkflowApi = parkSmartApi,
): ParkingWorkflow {
  const [candidates, setCandidates] = useState<RecommendationCandidate[]>([]);
  const [selectedSlotId, setSelectedSlotId] = useState<FloorScopedId | null>(null);
  const [activeRoute, setActiveRoute] = useState<RouteResult | null>(null);
  const [messages, setMessages] = useState<WorkflowMessage[]>([]);
  const [threadId, setThreadId] = useState(createDemoThreadId);
  const [pending, setPending] = useState<WorkflowAction | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
        "Ô vừa thay đổi hoặc không còn trống. Dữ liệu đã được tải lại; hãy chọn một đề xuất còn AVAILABLE và thử lại.",
      );
      return;
    }
    setNotice(vietnameseError(error));
  }

  function selectCandidate(slotId: FloorScopedId) {
    if (!candidates.some((candidate) => candidate.slot_id === slotId)) return;
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
    if (!slot || !candidates.some((candidate) => candidate.slot_id === slot.id)) {
      setNotice("Hãy chọn rõ một ô trong danh sách đề xuất trước khi giữ chỗ.");
      return;
    }
    setPending("reserve");
    setNotice(null);
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
      setNotice("Không có reservation đang hoạt động để xác nhận đỗ xe.");
      return;
    }
    setPending("confirm-parking");
    setNotice(null);
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
      setCandidates([]);
      setSelectedSlotId(null);
      setActiveRoute(null);
      setMessages([]);
      setThreadId(createDemoThreadId());
      await data.refresh();
    } catch (error) {
      await handleMutationFailure(error);
    } finally {
      setPending(null);
    }
  }

  async function sendAgentMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed) return;
    setMessages((current) => [...current, { role: "user", text: trimmed }]);
    setPending("chat");
    setNotice(null);
    try {
      const response = await api.chat({
        thread_id: threadId,
        user_id: MVP_DEMO_USER_ID,
        vehicle_id: MVP_DEMO_VEHICLE_ID,
        message: trimmed,
      });
      await data.refresh();
      setMessages((current) => [
        ...current,
        { role: "agent", text: response.message },
      ]);
      setCandidates(
        response.recommended_slot_ids.map((slot_id) => ({
          slot_id,
          score: 0,
          distance_m: 0,
          reasons: [],
        })),
      );
      setSelectedSlotId(response.selected_slot);
      setActiveRoute(response.route);
    } catch (error) {
      setNotice(vietnameseError(error));
    } finally {
      setPending(null);
    }
  }

  return {
    candidates,
    recommendedSlotIds: candidates.map((candidate) => candidate.slot_id),
    selectedSlotId,
    activeRoute,
    messages,
    threadId,
    pending,
    notice,
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
  };
}
