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
export type ActorType = "USER" | "SIMULATOR" | "CAMERA" | "SYSTEM";
export type ParkingEventType =
  | "VEHICLE_ENTERED"
  | "SLOT_RESERVED"
  | "RESERVATION_CANCELLED"
  | "RESERVATION_EXPIRED"
  | "VEHICLE_PARKED"
  | "VEHICLE_LEFT_SLOT"
  | "VEHICLE_EXITED";
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

export type AdjacentSlotObservedStatus = "AVAILABLE" | "OCCUPIED";

export interface AdjacentSlotObservationRequest {
  user_id: EntityId;
  observed_status: AdjacentSlotObservedStatus;
  expected_version: number;
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
  zone_id?: ZoneId | null;
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
  current_location?: FloorScopedId | null;
  message: string;
}

export type ChatUiActionStyle = "primary" | "secondary" | "danger";
export type ParkingPreference =
  | "ANY"
  | "EV"
  | "ACCESSIBLE"
  | "NEAR_ELEVATOR";

interface ChatUiActionBase<TType extends string, TPayload> {
  id: string;
  type: TType;
  label: string;
  payload: TPayload;
  style: ChatUiActionStyle;
  requires_confirmation: boolean;
}

export type ChatUiAction =
  | ChatUiActionBase<"SELECT_LOCATION", { node_id?: FloorScopedId }>
  | ChatUiActionBase<
      "SELECT_PARKING_PREFERENCE",
      { preference: ParkingPreference }
    >
  | ChatUiActionBase<"SELECT_SLOT", { slot_id: FloorScopedId }>
  | ChatUiActionBase<"RESERVE_AND_ROUTE", { slot_id: FloorScopedId }>
  | ChatUiActionBase<"CONFIRM_PARKING", Record<string, never>>
  | ChatUiActionBase<"FIND_VEHICLE", Record<string, never>>
  | ChatUiActionBase<"COMPLETE_SESSION", Record<string, never>>
  | ChatUiActionBase<
      "OPEN_WRONG_PARKING_REPORT",
      { slot_id?: FloorScopedId }
    >
  | ChatUiActionBase<"CANCEL", { slot_id?: FloorScopedId }>;

export interface ChatResponse {
  thread_id: string;
  message: string;
  intent: string | null;
  selected_slot: FloorScopedId | null;
  tool_names: string[];
  current_location: FloorScopedId | null;
  recommended_slot_ids: FloorScopedId[];
  route: RouteResult | null;
  ui_actions: ChatUiAction[];
}

export interface SpeechTranscriptionResponse {
  text: string;
}

export type SimulatorAction = "RESET" | "PARK" | "LEAVE";

export interface SimulatorStep {
  sequence: number;
  action: SimulatorAction;
  slot_id: FloorScopedId | null;
  vehicle_id: string | null;
  resulting_status: SlotStatus | null;
}

export interface SimulatorMutationRequest {
  slot_id: FloorScopedId;
  vehicle_id: EntityId;
}

export interface ParkingEvent {
  id: EntityId;
  event_type: ParkingEventType;
  slot_id: FloorScopedId | null;
  actor_type: ActorType;
  actor_id: EntityId | null;
  old_status: SlotStatus | null;
  new_status: SlotStatus | null;
  created_at: string;
  metadata: Record<string, unknown>;
}

export interface AdminEventFilters {
  limit?: number;
  zone_id?: ZoneId;
  event_type?: ParkingEventType;
  slot_id?: FloorScopedId;
}

export interface WrongParkingReport {
  id: EntityId;
  reporter_user_id: EntityId;
  slot_id: FloorScopedId;
  reason_code: WrongParkingReason;
  status: WrongParkingReportStatus;
  observed_plate_number: string | null;
  description: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
  version: number;
}

export type WrongParkingReportStatus = "OPEN" | "RESOLVED";
export type WrongParkingReason =
  | "WRONG_SLOT"
  | "CROSSED_LINE"
  | "BLOCKING_ACCESS"
  | "OCCUPYING_CHARGER"
  | "OTHER";

export interface CreateWrongParkingReportRequest {
  user_id: EntityId;
  slot_id: FloorScopedId;
  reason_code: WrongParkingReason;
  observed_plate_number?: string | null;
  description?: string | null;
}

export interface AdminReportFilters {
  status?: WrongParkingReportStatus;
  slotId?: FloorScopedId;
  limit?: number;
}

export interface ResolveWrongParkingReportRequest {
  status: "RESOLVED";
  resolution_note?: string | null;
  expected_version: number;
}
export type ResolveWrongParkingReportResponse = WrongParkingReport;

export interface ReopenWrongParkingReportRequest {
  expected_version: number;
}
export type ReopenWrongParkingReportResponse = WrongParkingReport;

export interface DeleteWrongParkingReportRequest {
  expected_version: number;
}

export interface DeleteWrongParkingReportResponse {
  deleted_report_id: EntityId;
}

export interface SlotFilters {
  zone_id?: ZoneId;
  status?: SlotStatus;
  has_charger?: boolean;
  is_accessible?: boolean;
}
