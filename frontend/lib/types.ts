export type EntityId = string;
export type FloorScopedId = string;
export type FloorId = "F1" | "F2" | "F3";
export type ZoneId = "A" | "B" | "C" | "D";

export type SlotStatus = "AVAILABLE" | "RESERVED" | "OCCUPIED";
export type ReservationStatus =
  | "ACTIVE"
  | "CONFIRMED"
  | "EXPIRED"
  | "CANCELLED";
export type ParkingSessionStatus = "ACTIVE" | "COMPLETED" | "CANCELLED";
export type ActorType = "USER" | "ADMIN" | "SIMULATOR" | "CAMERA" | "SYSTEM";
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
  | "RAMP"
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

export type ParkingSlotDefinition = Omit<
  ParkingSlot,
  "status" | "version" | "occupied_by_vehicle_id"
>;

export type AdjacentSlotObservedStatus = "AVAILABLE" | "OCCUPIED";

export interface AdjacentSlotObservationRequest {
  user_id: EntityId;
  observed_status: AdjacentSlotObservedStatus;
  expected_slot_version: number;
  evidence?: File;
}

export type SlotObservationStatus = "PENDING" | "VERIFIED" | "REJECTED" | "EXPIRED";
export type RewardSourceType =
  | "ADJACENT_SLOT_OBSERVATION"
  | "WRONG_PARKING_REPORT"
  | "VOUCHER_REDEMPTION";
export type RewardTransactionStatus = "PENDING" | "EARNED" | "CANCELLED" | "POSTED";
export type ParkingVoucherStatus = "ISSUED" | "APPLIED" | "EXPIRED" | "CANCELLED";

export interface SlotObservation {
  id: EntityId;
  observer_user_id: EntityId;
  observer_session_id: EntityId;
  slot_id: FloorScopedId;
  observed_status: AdjacentSlotObservedStatus;
  verification_status: SlotObservationStatus;
  reward_points: number;
  reward_status: RewardTransactionStatus | null;
  evidence_storage_path: string | null;
  evidence_content_type: string | null;
  evidence_size_bytes: number | null;
  observed_slot_version: number;
  created_at: string;
  expires_at: string;
  verified_at: string | null;
  verified_by: string | null;
  rejection_reason: string | null;
  version: number;
}

export interface RewardSummary {
  available_points: number;
  pending_points: number;
  verified_contributions: number;
  daily_pending_points: number;
  daily_earned_points: number;
  daily_limit_points: number;
}

export interface RewardConfiguration {
  adjacent_observation_reward_points: number;
  wrong_parking_report_reward_points: number;
  contribution_daily_points_limit: number;
  redemption_enabled: boolean;
}

export type RewardTransactionType =
  | "CONTRIBUTION_REWARD"
  | "REWARD_REVERSAL"
  | "ADMIN_ADJUSTMENT"
  | "VOUCHER_REDEMPTION"
  | "VOUCHER_REFUND";

export interface RewardTransaction {
  id: EntityId;
  user_id: EntityId;
  source_type: RewardSourceType;
  source_reference: EntityId;
  transaction_type: RewardTransactionType;
  status: RewardTransactionStatus;
  points_delta: number;
  created_at: string;
  settled_at: string | null;
  metadata: Record<string, unknown>;
}

export interface RewardCatalogItem {
  id: EntityId;
  code: string;
  name: string;
  points_cost: number;
  free_minutes: number;
  validity_days: number;
  version: number;
}

export interface ParkingVoucher {
  id: EntityId;
  redemption_id: EntityId;
  catalog_code_snapshot: string;
  points_cost_snapshot: number;
  free_minutes_snapshot: number;
  validity_days_snapshot: number;
  status: ParkingVoucherStatus;
  issued_at: string;
  expires_at: string;
  applied_at: string | null;
  applied_session_id: EntityId | null;
}

export interface ParkingTimeBenefit {
  voucher_id: EntityId | null;
  total_minutes: number;
  free_minutes: number;
  billable_minutes: number;
}

export interface CompletedParkingSession extends ParkingSession {
  time_benefit: ParkingTimeBenefit;
}

export interface RewardRedemptionResult {
  redemption: {
    id: EntityId;
    catalog_item_id: EntityId;
    points_cost_snapshot: number;
    free_minutes_snapshot: number;
    validity_days_snapshot: number;
    status: "COMPLETED" | "REFUNDED";
    created_at: string;
  };
  voucher: ParkingVoucher;
  available_points: number;
}

export interface ContributionRecord {
  id: EntityId;
  source_type: RewardSourceType;
  source_reference: EntityId;
  observer_session_id: EntityId | null;
  floor_id: FloorId;
  slot_id: FloorScopedId;
  points: number;
  status: RewardTransactionStatus | null;
  created_at: string;
  settled_at: string | null;
}

export interface MapNode {
  id: FloorScopedId;
  floor_id: FloorId;
  type: MapNodeType;
  x: number;
  y: number;
}

export type RouteMode = "VEHICLE" | "PEDESTRIAN";

export interface MapEdge {
  from_node: FloorScopedId;
  to_node: FloorScopedId;
  distance_m: number;
  bidirectional: boolean;
  enabled: boolean;
  allowed_mode: RouteMode | null;
}

export interface ParkingMap {
  nodes: MapNode[];
  edges: MapEdge[];
  slots: ParkingSlotDefinition[];
}

export interface ParkingStatus {
  total: number;
  available: number;
  reserved: number;
  occupied: number;
  by_zone: Record<ZoneId, Record<SlotStatus, number>>;
}

export interface ParkingSnapshot {
  slots: ParkingSlot[];
  status: ParkingStatus;
  state_version: number;
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
  floor_id?: FloorId | null;
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
  mode: RouteMode;
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

export interface UserParkingState {
  current_location: Location | null;
  active_reservation: ParkingReservation | null;
  active_session: ActiveParkingSession | null;
  reward_summary: RewardSummary;
  reward_configuration: RewardConfiguration;
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
  evidence_storage_path: string | null;
  evidence_content_type: string | null;
  evidence_size_bytes: number | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
  verification_outcome: WrongParkingReportVerificationOutcome;
  reward_points: number;
  reward_status: RewardTransactionStatus | null;
  duplicate_candidate_of_id: EntityId | null;
  version: number;
}

export type WrongParkingReportStatus = "OPEN" | "RESOLVED";
export type WrongParkingReportVerificationOutcome =
  | "PENDING"
  | "CONFIRMED"
  | "REJECTED"
  | "DUPLICATE"
  | "UNVERIFIABLE";
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
  evidence?: File;
}

export interface AdminReportFilters {
  status?: WrongParkingReportStatus;
  slotId?: FloorScopedId;
  limit?: number;
}

export interface ResolveWrongParkingReportRequest {
  status: "RESOLVED";
  verification_outcome: Exclude<WrongParkingReportVerificationOutcome, "PENDING">;
  resolution_note?: string | null;
  expected_version: number;
}

export interface AdminObservationFilters {
  status?: SlotObservationStatus;
  floorId?: FloorId;
  slotId?: FloorScopedId;
  userId?: EntityId;
  limit?: number;
}

export interface VerifySlotObservationRequest {
  expected_version: number;
}

export interface RejectSlotObservationRequest {
  expected_version: number;
  reason?: string | null;
}

export interface UpdateParkingSlotStatusRequest {
  status: Exclude<SlotStatus, "RESERVED">;
  expected_version: number;
}
export type ResolveWrongParkingReportResponse = WrongParkingReport;

export interface ReopenWrongParkingReportRequest {
  expected_version: number;
}
export type ReopenWrongParkingReportResponse = WrongParkingReport;

export interface ReportEvidenceUrlResponse {
  signed_url: string;
  expires_in: number;
}

export interface ObservationEvidenceUrlResponse {
  signed_url: string;
  expires_in: number;
}

export interface AddVehicleRequest {
  plate_number: string;
  requires_charging: boolean;
}

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
