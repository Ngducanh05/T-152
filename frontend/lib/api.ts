import type { AuthenticatedProfile } from "./auth";
import type {
  ActiveParkingSession,
  AddVehicleRequest,
  AdjacentSlotObservationRequest,
  AdminObservationFilters,
  AdminReportFilters,
  AdminEventFilters,
  ApiEnvelope,
  ApiFailure,
  ChatRequest,
  ChatResponse,
  CompleteSessionRequest,
  CreateWrongParkingReportRequest,
  DeleteWrongParkingReportRequest,
  DeleteWrongParkingReportResponse,
  ConfirmLocationRequest,
  ScanLocationRequest,
  ScannedLocation,
  ConfirmParkingRequest,
  CreateReservationRequest,
  Location,
  ParkingMap,
  ParkingEvent,
  ParkingReservation,
  ParkingSession,
  ParkingSlot,
  ParkingSnapshot,
  ParkingStatus,
  ContributionRecord,
  RejectSlotObservationRequest,
  RecommendationRequest,
  RecommendationResult,
  ReopenWrongParkingReportRequest,
  ReopenWrongParkingReportResponse,
  ReportEvidenceUrlResponse,
  ResolveWrongParkingReportRequest,
  ResolveWrongParkingReportResponse,
  RouteRequest,
  RouteResponse,
  RewardConfiguration,
  RewardSummary,
  SimulatorStep,
  SimulatorMutationRequest,
  SlotFilters,
  SpeechTranscriptionResponse,
  SlotObservation,
  VerifySlotObservationRequest,
  UpdateParkingSlotStatusRequest,
  WrongParkingReport,
  UserParkingState,
} from "./types";

const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";

export interface DatabaseHealth {
  database: string;
}

export interface ApiAuthProvider {
  getAccessToken: () => Promise<string | null>;
  refreshAccessToken: () => Promise<string | null>;
  onAuthenticationFailure?: () => Promise<void> | void;
}

export class ApiError extends Error {
  readonly code: string;
  readonly requestId: string | null;
  readonly status: number;
  readonly details: Record<string, unknown> | null;

  constructor(options: {
    code: string;
    message: string;
    requestId?: string | null;
    status: number;
    details?: Record<string, unknown> | null;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.code = options.code;
    this.requestId = options.requestId ?? null;
    this.status = options.status;
    this.details = options.details ?? null;
  }
}

export function formatApiErrorForOperator(
  error: unknown,
  userMessage = "Không thể hoàn tất yêu cầu.",
): string {
  if (!(error instanceof ApiError)) {
    return "Không thể kết nối tới ParkSmart API. Vui lòng thử lại.";
  }

  const requestReference = error.requestId
    ? ` Mã yêu cầu: ${error.requestId}.`
    : "";
  return `${userMessage} Mã lỗi: ${error.code}.${requestReference}`;
}

function isFailureEnvelope(value: unknown): value is ApiFailure {
  if (!value || typeof value !== "object") return false;
  const envelope = value as Partial<ApiFailure>;
  const error = envelope.error;
  return (
    envelope.success === false &&
    !!error &&
    typeof error.code === "string" &&
    typeof error.message === "string" &&
    typeof error.request_id === "string"
  );
}

function isSuccessEnvelope<T>(value: unknown): value is ApiEnvelope<T> & { success: true } {
  return (
    !!value &&
    typeof value === "object" &&
    (value as { success?: unknown }).success === true &&
    "data" in value
  );
}

export async function parseApiResponse<T>(response: Response): Promise<T> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError({
      code: "INVALID_API_RESPONSE",
      message: "The API returned an invalid JSON response.",
      status: response.status,
    });
  }

  if (isFailureEnvelope(body)) {
    throw new ApiError({
      code: body.error.code,
      message: body.error.message,
      requestId: body.error.request_id,
      status: response.status,
      details: body.error.details,
    });
  }

  if (!isSuccessEnvelope<T>(body) || !response.ok) {
    throw new ApiError({
      code: `HTTP_${response.status}`,
      message: "The API returned an unexpected response.",
      status: response.status,
    });
  }

  return body.data;
}

function queryString(values: Record<string, string | number | boolean | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

function idempotencyHeaders(
  idempotencyKey?: string,
): HeadersInit | undefined {
  if (!idempotencyKey) return undefined;

  return {
    "Idempotency-Key": idempotencyKey,
  };
}

export class ParkSmartApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;
  private authProvider: ApiAuthProvider | null;

  constructor(
    options: {
      baseUrl?: string;
      fetcher?: typeof fetch;
      authProvider?: ApiAuthProvider | null;
    } = {},
  ) {
    this.baseUrl = (options.baseUrl ?? DEFAULT_API_BASE_URL).replace(/\/$/, "");
    if (options.fetcher) {
      this.fetcher = options.fetcher;
    } else if (typeof window !== "undefined") {
      this.fetcher = (input, init) => window.fetch(input, init);
    } else {
      this.fetcher = (input, init) => globalThis.fetch(input, init);
    }
    this.authProvider = options.authProvider ?? null;
  }

  setAuthProvider(provider: ApiAuthProvider | null) {
    this.authProvider = provider;
  }

  private async fetchOnce(
    path: string,
    options: RequestInit,
    accessToken: string | null,
  ) {
    const headers = new Headers(options.headers);
    if (
      options.body !== undefined &&
      !(typeof FormData !== "undefined" && options.body instanceof FormData) &&
      !headers.has("Content-Type")
    ) {
      headers.set("Content-Type", "application/json");
    }
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    return this.fetcher(`${this.baseUrl}${path}`, { ...options, headers });
  }

  private async authenticatedFetch(path: string, options: RequestInit = {}) {
    const provider = this.authProvider;
    const accessToken = provider ? await provider.getAccessToken() : null;
    let response = await this.fetchOnce(path, options, accessToken);
    if (response.status !== 401 || !provider) return response;

    const refreshedToken = await provider.refreshAccessToken();
    if (!refreshedToken) {
      await provider.onAuthenticationFailure?.();
      return response;
    }
    response = await this.fetchOnce(path, options, refreshedToken);
    if (response.status === 401) await provider.onAuthenticationFailure?.();
    return response;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    const response = await this.authenticatedFetch(path, options);
    return parseApiResponse<T>(response);
  }

  private async optional<T>(request: Promise<T>): Promise<T | null> {
    try {
      return await request;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  }

  async checkDatabaseHealth(signal?: AbortSignal): Promise<DatabaseHealth> {
    const response = await this.fetchOnce("/health/database", { signal }, null);
    return parseApiResponse<DatabaseHealth>(response);
  }

  getCurrentUser(signal?: AbortSignal) {
    return this.request<AuthenticatedProfile>("/auth/me", { signal });
  }

  onboardCurrentUser(signal?: AbortSignal) {
    return this.request<AuthenticatedProfile>("/auth/onboarding", {
      method: "POST",
      body: JSON.stringify({}),
      signal,
    });
  }

  addVehicle(payload: AddVehicleRequest, signal?: AbortSignal) {
    return this.request<AuthenticatedProfile>("/auth/vehicles", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  }

  getMap(signal?: AbortSignal) {
    return this.request<ParkingMap>("/parking/map", { signal });
  }

  getParkingStatus(signal?: AbortSignal) {
    return this.request<ParkingStatus>("/parking/status", { signal });
  }

  getParkingSnapshot(signal?: AbortSignal) {
    return this.request<ParkingSnapshot>("/parking/snapshot", { signal });
  }

  getUserParkingState(userId: string, signal?: AbortSignal) {
    return this.request<UserParkingState>(
      `/parking/users/${encodeURIComponent(userId)}/state`,
      { signal },
    );
  }

  getSlots(filters: SlotFilters = {}, signal?: AbortSignal) {
    const query = queryString({
      zone_id: filters.zone_id,
      status: filters.status,
      has_charger: filters.has_charger,
      is_accessible: filters.is_accessible,
    });
    return this.request<ParkingSlot[]>(
      `/parking/slots${query}`,
      { signal },
    );
  }

  getSlot(slotId: string, signal?: AbortSignal) {
    return this.request<ParkingSlot>(
      `/parking/slots/${encodeURIComponent(slotId)}`,
      { signal },
    );
  }

  getCurrentLocation(userId: string, signal?: AbortSignal) {
    return this.optional(
      this.request<Location>(
        `/locations/current${queryString({ user_id: userId })}`,
        { signal },
      ),
    );
  }

  confirmLocation(payload: ConfirmLocationRequest, signal?: AbortSignal) {
    return this.request<Location>("/locations/confirm", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  }

  scanLocation(payload: ScanLocationRequest, signal?: AbortSignal) {
    return this.request<ScannedLocation>("/locations/scan", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  }

  recommend(payload: RecommendationRequest, signal?: AbortSignal) {
    return this.request<RecommendationResult>("/recommendations", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  }

  createReservation(
    payload: CreateReservationRequest,
    signal?: AbortSignal,
    idempotencyKey?: string,
  ) {
    return this.request<ParkingReservation>("/reservations", {
      method: "POST",
      body: JSON.stringify(payload),
      headers: idempotencyHeaders(idempotencyKey),
      signal,
    });
  }

  getActiveReservation(userId: string, signal?: AbortSignal) {
    return this.optional(
      this.request<ParkingReservation>(
        `/reservations/active${queryString({ user_id: userId })}`,
        { signal },
      ),
    );
  }

  cancelReservation(reservationId: string, userId: string, signal?: AbortSignal) {
    return this.request<ParkingReservation>(
      `/reservations/${encodeURIComponent(reservationId)}${queryString({ user_id: userId })}`,
      { method: "DELETE", signal },
    );
  }

  getRoute(payload: RouteRequest, signal?: AbortSignal) {
    return this.request<RouteResponse>("/routes", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  }

  confirmParking(
    payload: ConfirmParkingRequest,
    signal?: AbortSignal,
    idempotencyKey?: string,
  ) {
    return this.request<ParkingSession>("/sessions/confirm-parking", {
      method: "POST",
      body: JSON.stringify(payload),
      headers: idempotencyHeaders(idempotencyKey),
      signal,
    });
  }

  getActiveSession(userId: string, signal?: AbortSignal) {
    return this.optional(
      this.request<ActiveParkingSession>(
        `/sessions/active${queryString({ user_id: userId })}`,
        { signal },
      ),
    );
  }

  completeSession(
    sessionId: string,
    payload: CompleteSessionRequest,
    signal?: AbortSignal,
    idempotencyKey?: string,
  ) {
    return this.request<ParkingSession>(
      `/sessions/${encodeURIComponent(sessionId)}/complete`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        headers: idempotencyHeaders(idempotencyKey),
        signal,
      },
    );
  }

  chat(payload: ChatRequest, signal?: AbortSignal) {
    return this.request<ChatResponse>("/agent/chat", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  }

  observeAdjacentSlot(
    slotId: string,
    payload: AdjacentSlotObservationRequest,
    signal?: AbortSignal,
  ) {
    return this.request<SlotObservation>(
      `/parking/slots/${encodeURIComponent(slotId)}/observation`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        signal,
      },
    );
  }

  async transcribeSpeech(audio: Blob, signal?: AbortSignal) {
    const response = await this.authenticatedFetch("/speech/transcriptions", {
      method: "POST",
      body: audio,
      headers: { "Content-Type": audio.type || "audio/webm" },
      signal,
    });
    return parseApiResponse<SpeechTranscriptionResponse>(response);
  }

  resetDemo(signal?: AbortSignal) {
    return this.request<SimulatorStep[]>("/simulator/reset", {
      method: "POST",
      body: JSON.stringify({}),
      signal,
    });
  }

  parkSimulatedVehicle(payload: SimulatorMutationRequest, signal?: AbortSignal) {
    return this.request<ParkingSlot>("/simulator/park", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  }

  leaveSimulatedVehicle(payload: SimulatorMutationRequest, signal?: AbortSignal) {
    return this.request<ParkingSlot>("/simulator/leave", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  }

  runFixedScenario(signal?: AbortSignal) {
    return this.request<SimulatorStep[]>("/simulator/run-scenario", {
      method: "POST",
      body: JSON.stringify({}),
      signal,
    });
  }

  getAdminEvents(filters: AdminEventFilters = {}, signal?: AbortSignal) {
    const query = queryString({
      limit: filters.limit,
      zone_id: filters.zone_id,
      event_type: filters.event_type,
      slot_id: filters.slot_id,
    });
    return this.request<ParkingEvent[]>(`/admin/events${query}`, { signal });
  }

  reportWrongParking(
    payload: CreateWrongParkingReportRequest,
    signal?: AbortSignal,
    idempotencyKey?: string,
  ) {
    const headers = idempotencyHeaders(idempotencyKey);

    if (payload.evidence) {
      const form = new FormData();
      form.set("user_id", payload.user_id);
      form.set("slot_id", payload.slot_id);
      form.set("reason_code", payload.reason_code);
      if (payload.observed_plate_number) {
        form.set("observed_plate_number", payload.observed_plate_number);
      }
      if (payload.description) form.set("description", payload.description);
      form.set("evidence", payload.evidence);
      return this.request<WrongParkingReport>("/reports/wrong-parking", {
        method: "POST",
        body: form,
        headers,
        signal,
      });
    }
    return this.request<WrongParkingReport>("/reports/wrong-parking", {
      method: "POST",
      body: JSON.stringify(payload),
      headers,
      signal,
    });
  }

  getAdminReports(filters: AdminReportFilters = {}, signal?: AbortSignal) {
    const query = queryString({
      status: filters.status,
      slot_id: filters.slotId,
      limit: filters.limit ?? 20,
    });
    return this.request<WrongParkingReport[]>(`/admin/reports${query}`, {
      signal,
    });
  }

  updateAdminSlotStatus(
    slotId: string,
    payload: UpdateParkingSlotStatusRequest,
    signal?: AbortSignal,
  ) {
    return this.request<ParkingSlot>(
      `/admin/parking/slots/${encodeURIComponent(slotId)}/status`,
      { method: "PATCH", body: JSON.stringify(payload), signal },
    );
  }

  getAdminObservations(
    filters: AdminObservationFilters = {},
    signal?: AbortSignal,
  ) {
    const query = queryString({
      status: filters.status,
      floor_id: filters.floorId,
      slot_id: filters.slotId,
      user_id: filters.userId,
      limit: filters.limit ?? 50,
    });
    return this.request<SlotObservation[]>(
      `/admin/slot-observations${query}`,
      { signal },
    );
  }

  getAdminObservation(observationId: string, signal?: AbortSignal) {
    return this.request<SlotObservation>(
      `/admin/slot-observations/${encodeURIComponent(observationId)}`,
      { signal },
    );
  }

  verifyAdminObservation(
    observationId: string,
    payload: VerifySlotObservationRequest,
    signal?: AbortSignal,
  ) {
    return this.request<SlotObservation>(
      `/admin/slot-observations/${encodeURIComponent(observationId)}/verify`,
      { method: "POST", body: JSON.stringify(payload), signal },
    );
  }

  rejectAdminObservation(
    observationId: string,
    payload: RejectSlotObservationRequest,
    signal?: AbortSignal,
  ) {
    return this.request<SlotObservation>(
      `/admin/slot-observations/${encodeURIComponent(observationId)}/reject`,
      { method: "POST", body: JSON.stringify(payload), signal },
    );
  }

  getRewardSummary(userId: string, signal?: AbortSignal) {
    return this.request<RewardSummary>(
      `/rewards/users/${encodeURIComponent(userId)}/summary`,
      { signal },
    );
  }

  getRewardConfiguration(signal?: AbortSignal) {
    return this.request<RewardConfiguration>("/rewards/configuration", {
      signal,
    });
  }

  getUserContributions(userId: string, signal?: AbortSignal) {
    return this.request<ContributionRecord[]>(
      `/contributions/users/${encodeURIComponent(userId)}`,
      { signal },
    );
  }

  getAdminReport(reportId: string, signal?: AbortSignal) {
    return this.request<WrongParkingReport>(
      `/admin/reports/${encodeURIComponent(reportId)}`,
      { signal },
    );
  }

  resolveAdminReport(
    reportId: string,
    payload: ResolveWrongParkingReportRequest,
    signal?: AbortSignal,
  ) {
    return this.request<ResolveWrongParkingReportResponse>(
      `/admin/reports/${encodeURIComponent(reportId)}`,
      { method: "PATCH", body: JSON.stringify(payload), signal },
    );
  }

  reopenAdminReport(
    reportId: string,
    payload: ReopenWrongParkingReportRequest,
    signal?: AbortSignal,
  ) {
    return this.request<ReopenWrongParkingReportResponse>(
      `/admin/reports/${encodeURIComponent(reportId)}/reopen`,
      { method: "POST", body: JSON.stringify(payload), signal },
    );
  }

  getAdminReportEvidenceUrl(reportId: string, signal?: AbortSignal) {
    return this.request<ReportEvidenceUrlResponse>(
      `/admin/reports/${encodeURIComponent(reportId)}/evidence-url`,
      { signal },
    );
  }

  deleteAdminReport(
    reportId: string,
    payload: DeleteWrongParkingReportRequest,
    signal?: AbortSignal,
  ) {
    const query = queryString({ expected_version: payload.expected_version });
    return this.request<DeleteWrongParkingReportResponse>(
      `/admin/reports/${encodeURIComponent(reportId)}${query}`,
      { method: "DELETE", signal },
    );
  }
}

export const parkSmartApi = new ParkSmartApiClient({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL,
});
