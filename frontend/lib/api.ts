import type {
  ActiveParkingSession,
  ApiEnvelope,
  ApiFailure,
  ChatRequest,
  ChatResponse,
  CompleteSessionRequest,
  ConfirmLocationRequest,
  ConfirmParkingRequest,
  CreateReservationRequest,
  Location,
  ParkingMap,
  ParkingReservation,
  ParkingSession,
  ParkingSlot,
  ParkingStatus,
  RecommendationRequest,
  RecommendationResult,
  RouteRequest,
  RouteResponse,
  SimulatorStep,
  SlotFilters,
} from "./types";

const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";

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

export class ParkSmartApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;

  constructor(options: { baseUrl?: string; fetcher?: typeof fetch } = {}) {
    this.baseUrl = (options.baseUrl ?? DEFAULT_API_BASE_URL).replace(/\/$/, "");
    this.fetcher = options.fetcher ?? fetch;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    const headers = new Headers(options.headers);
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    const fetcher = this.fetcher;
    const response = await fetcher(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    });
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

  getMap(signal?: AbortSignal) {
    return this.request<ParkingMap>("/parking/map", { signal });
  }

  getParkingStatus(signal?: AbortSignal) {
    return this.request<ParkingStatus>("/parking/status", { signal });
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

  recommend(payload: RecommendationRequest, signal?: AbortSignal) {
    return this.request<RecommendationResult>("/recommendations", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  }

  createReservation(payload: CreateReservationRequest, signal?: AbortSignal) {
    return this.request<ParkingReservation>("/reservations", {
      method: "POST",
      body: JSON.stringify(payload),
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

  confirmParking(payload: ConfirmParkingRequest, signal?: AbortSignal) {
    return this.request<ParkingSession>("/sessions/confirm-parking", {
      method: "POST",
      body: JSON.stringify(payload),
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
  ) {
    return this.request<ParkingSession>(
      `/sessions/${encodeURIComponent(sessionId)}/complete`,
      {
        method: "POST",
        body: JSON.stringify(payload),
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

  resetDemo(signal?: AbortSignal) {
    return this.request<SimulatorStep[]>("/simulator/reset", {
      method: "POST",
      body: JSON.stringify({}),
      signal,
    });
  }
}

export const parkSmartApi = new ParkSmartApiClient({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL,
});
