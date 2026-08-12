export type EntityId = string;
export type FloorScopedId = string;
export type FloorId = "F1";
export type ZoneId = "A" | "B" | "C" | "D";

export type SlotStatus = "AVAILABLE" | "RESERVED" | "OCCUPIED";
export type ReservationStatus =
  | "ACTIVE"
  | "CONFIRMED"
  | "EXPIRED"
  | "CANCELLED";
export type ParkingSessionStatus = "ACTIVE" | "COMPLETED" | "CANCELLED";
export type MapNodeType =
  | "ENTRANCE"
  | "EXIT"
  | "CHECKPOINT"
  | "ELEVATOR"
  | "AISLE"
  | "SLOT";

export interface ApiErrorDetail {
  code: string;
  message: string;
  request_id: string;
  details?: Record<string, unknown> | null;
}

export interface ApiSuccess<T> {
  success: true;
  data: T;
  message: string | null;
}

export interface ApiFailure {
  success: false;
  error: ApiErrorDetail;
}

export type ApiEnvelope<T> = ApiSuccess<T> | ApiFailure;

export interface ParkingSlot {
  id: FloorScopedId;
  floor_id: FloorId;
  zone_id: ZoneId;
  node_id: FloorScopedId;
  status: SlotStatus;
  has_charger: boolean;
  is_accessible: boolean;
  version: number;
  occupied_by_vehicle_id: EntityId | null;
}

export interface MapNode {
  id: FloorScopedId;
  floor_id: FloorId;
  type: MapNodeType;
  x: number;
  y: number;
}

export interface MapEdge {
  from_node: FloorScopedId;
  to_node: FloorScopedId;
  distance_m: number;
  bidirectional: boolean;
  enabled: boolean;
}

export interface ParkingMap {
  nodes: MapNode[];
  edges: MapEdge[];
  slots: ParkingSlot[];
}

export interface ParkingStatus {
  total: number;
  available: number;
  reserved: number;
  occupied: number;
  by_zone: Record<ZoneId, Record<SlotStatus, number>>;
}

export interface Location {
  user_id: EntityId;
  node_id: FloorScopedId;
}

export interface ConfirmLocationRequest {
  user_id: EntityId;
  node_id: FloorScopedId;
}

export interface RecommendationRequest {
  user_id: EntityId;
  start_node_id: FloorScopedId;
  charging_required?: boolean;
  accessible_required?: boolean;
  near_elevator?: boolean;
  limit?: number;
}

export interface RecommendationCandidate {
  slot_id: FloorScopedId;
  score: number;
  distance_m: number;
  reasons: string[];
}

export interface RecommendationResult {
  recommendations: RecommendationCandidate[];
  parking_state_version: number;
}

export interface ParkingReservation {
  id: EntityId;
  user_id: EntityId;
  vehicle_id: EntityId;
  slot_id: FloorScopedId;
  status: ReservationStatus;
  expires_at: string;
  created_at: string;
}

export interface CreateReservationRequest {
  user_id: EntityId;
  vehicle_id: EntityId;
  slot_id: FloorScopedId;
  expected_version?: number | null;
}

export interface RouteResult {
  path: FloorScopedId[];
  distance_m: number;
  polyline: [number, number][];
}

export interface RouteRequest {
  start_node_id: FloorScopedId;
  destination_node_id: FloorScopedId;
}

export interface RouteResponse extends RouteResult {
  start_node_id: FloorScopedId;
  destination_node_id: FloorScopedId;
}

export interface ParkingSession {
  id: EntityId;
  user_id: EntityId;
  vehicle_id: EntityId;
  slot_id: FloorScopedId;
  status: ParkingSessionStatus;
  parked_at: string;
  completed_at: string | null;
}

export interface ConfirmParkingRequest {
  user_id: EntityId;
  vehicle_id: EntityId;
  reservation_id: EntityId;
  expected_version?: number | null;
}

export interface ActiveParkingSession {
  session_id: EntityId;
  vehicle_id: EntityId;
  slot_id: FloorScopedId;
  destination_node_id: FloorScopedId;
}

export interface CompleteSessionRequest {
  user_id: EntityId;
  expected_version?: number | null;
}

export interface ChatRequest {
  thread_id: string;
  user_id: EntityId;
  vehicle_id?: EntityId | null;
  message: string;
}

export interface ChatResponse {
  thread_id: string;
  message: string;
  intent: string | null;
  selected_slot: FloorScopedId | null;
  tool_names: string[];
  current_location: FloorScopedId | null;
  recommended_slot_ids: FloorScopedId[];
  route: RouteResult | null;
}

export type SimulatorAction = "RESET" | "PARK" | "LEAVE";

export interface SimulatorStep {
  sequence: number;
  action: SimulatorAction;
  slot_id: FloorScopedId | null;
  vehicle_id: string | null;
  resulting_status: SlotStatus | null;
}

export interface SlotFilters {
  zone_id?: ZoneId;
  status?: SlotStatus;
  has_charger?: boolean;
  is_accessible?: boolean;
}
