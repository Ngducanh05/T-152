import type {
  ActiveParkingSession,
  ApiEnvelope,
  ChatResponse,
  Location,
  MapEdge,
  MapNode,
  ParkingMap,
  ParkingReservation,
  ParkingSlot,
  ParkingStatus,
  RecommendationResult,
  RouteResponse,
  SlotStatus,
  ZoneId,
} from "@/lib/types";

export const TEST_USER_ID = "USER-001";
export const TEST_VEHICLE_ID = "VEHICLE-001";

const zones: ZoneId[] = ["A", "B", "C", "D"];

type TestParkingMap = Omit<ParkingMap, "slots"> & { slots: ParkingSlot[] };

export function createCanonicalMap(): TestParkingMap {
  const nodes: MapNode[] = [
    { id: "F1-ENTRANCE", floor_id: "F1", type: "ENTRANCE", x: 0, y: 50 },
    { id: "F1-CP1", floor_id: "F1", type: "CHECKPOINT", x: 15, y: 50 },
  ];
  const edges: MapEdge[] = [
    {
      from_node: "F1-ENTRANCE",
      to_node: "F1-CP1",
      distance_m: 15,
      bidirectional: true,
      enabled: true,
      allowed_mode: null,
    },
  ];
  const slots: ParkingSlot[] = [];

  for (const zoneId of zones) {
    const north = zoneId === "A" || zoneId === "B";
    const aisleX = zoneId === "A" || zoneId === "C" ? 25 : 58;
    const aisleId = `F1-${zoneId}-W`;
    nodes.push({
      id: aisleId,
      floor_id: "F1",
      type: "AISLE",
      x: aisleX,
      y: north ? 30 : 70,
    });
    edges.push({
      from_node: "F1-CP1",
      to_node: aisleId,
      distance_m: 20,
      bidirectional: true,
      enabled: true,
      allowed_mode: null,
    });

    for (let index = 1; index <= 10; index += 1) {
      const id = `F1-${zoneId}${String(index).padStart(2, "0")}`;
      const status: SlotStatus =
        id === "F1-A01"
          ? "RESERVED"
          : id === "F1-B01"
            ? "OCCUPIED"
            : "AVAILABLE";
      const slot: ParkingSlot = {
        id,
        floor_id: "F1",
        zone_id: zoneId,
        node_id: aisleId,
        status,
        has_charger: (zoneId === "C" || zoneId === "D") && index <= 5,
        is_accessible: id === "F1-D10",
        version: status === "AVAILABLE" ? 7 : 8,
        occupied_by_vehicle_id:
          status === "OCCUPIED" ? TEST_VEHICLE_ID : null,
      };
      slots.push(slot);
      nodes.push({
        id,
        floor_id: "F1",
        type: "SLOT",
        x: aisleX + ((index - 1) % 5) * 4.25,
        y: north ? (index <= 5 ? 22 : 26) : index <= 5 ? 74 : 78,
      });
      edges.push({
        from_node: aisleId,
        to_node: id,
        distance_m: 4,
        bidirectional: true,
        enabled: true,
        allowed_mode: null,
      });
    }
  }

  return { nodes, edges, slots };
}

export const canonicalMap = createCanonicalMap();

export const parkingStatus: ParkingStatus = {
  total: 40,
  available: 38,
  reserved: 1,
  occupied: 1,
  by_zone: {
    A: { AVAILABLE: 9, RESERVED: 1, OCCUPIED: 0 },
    B: { AVAILABLE: 9, RESERVED: 0, OCCUPIED: 1 },
    C: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
    D: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
  },
};

export const currentLocation: Location = {
  user_id: TEST_USER_ID,
  node_id: "F1-ENTRANCE",
};

export const recommendationResponse: RecommendationResult = {
  recommendations: [
    {
      slot_id: "F1-D01",
      score: 92,
      distance_m: 76,
      reasons: ["Có sạc EV", "Gần thang máy"],
    },
  ],
  parking_state_version: 12,
};

export const routeResponse: RouteResponse = {
  start_node_id: "F1-ENTRANCE",
  destination_node_id: "F1-D01",
  path: ["F1-ENTRANCE", "F1-CP1", "F1-D-W", "F1-D01"],
  distance_m: 76,
  polyline: [
    [0, 50],
    [15, 50],
    [58, 70],
    [58, 74],
  ],
};

export const activeReservation: ParkingReservation = {
  id: "RESERVATION-001",
  user_id: TEST_USER_ID,
  vehicle_id: TEST_VEHICLE_ID,
  slot_id: "F1-A01",
  status: "ACTIVE",
  expires_at: "2026-08-12T12:10:00Z",
  created_at: "2026-08-12T12:05:00Z",
};

export const activeSession: ActiveParkingSession = {
  session_id: "SESSION-001",
  vehicle_id: TEST_VEHICLE_ID,
  slot_id: "F1-B01",
  destination_node_id: "F1-B01",
};

export const agentChatResponse: ChatResponse = {
  thread_id: "thread-fixture",
  message: "Tôi đã tìm thấy ô phù hợp và đường đi.",
  intent: "recommend_and_route",
  selected_slot: "F1-D01",
  tool_names: ["recommend_parking_slot", "get_route"],
  current_location: "F1-ENTRANCE",
  recommended_slot_ids: ["F1-D01"],
  route: routeResponse,
  ui_actions: [],
};

export function successEnvelope<T>(data: T): ApiEnvelope<T> {
  return { success: true, data, message: null };
}

export function errorEnvelope(
  code: string,
  message: string,
  requestId = "request-fixture",
): ApiEnvelope<never> {
  return {
    success: false,
    error: { code, message, request_id: requestId },
  };
}

export const safeErrorEnvelopes = {
  slotConflict: errorEnvelope(
    "SLOT_NOT_AVAILABLE",
    "Ô đỗ vừa thay đổi. Vui lòng tải lại và chọn ô khác.",
    "request-conflict",
  ),
  agentUnavailable: errorEnvelope(
    "AGENT_TOOL_UNAVAILABLE",
    "Trợ lý ParkSmart đang tạm thời không khả dụng.",
    "request-agent-unavailable",
  ),
};

export function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function successResponse<T>(data: T, status = 200) {
  return jsonResponse(successEnvelope(data), status);
}

export function errorResponse(
  code: string,
  message: string,
  status: number,
  requestId = "request-fixture",
) {
  return jsonResponse(errorEnvelope(code, message, requestId), status);
}
