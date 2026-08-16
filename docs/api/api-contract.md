# ParkSmart AI API contract

## Status and scope

This document defines the shared Phase 0 identifiers, enums, Pydantic data contracts, and response envelopes. It does not define ORM models, database migrations, repositories, transactions, or parking business logic.

ADR-001 remains authoritative for the meaning and lifecycle of RESERVED.

## Shared conventions

- JSON field names use snake_case exactly as defined by the Pydantic models. No camelCase aliases are provided.
- Floor-scoped identifiers start with F1-, for example F1-A01, F1-CP2, and F1-ELEVATOR. The only MVP floor_id is F1.
- User, vehicle, reservation, session, and event identifiers use their domain prefixes, for example USER-001, VEHICLE-001, RESERVATION-001, SESSION-001, and EVENT-001.
- Timestamps are timezone-aware UTC values serialized as ISO 8601, for example 2026-08-11T08:30:00Z.
- Distances use metres and the field name distance_m.
- Enum values are serialized as the uppercase strings listed below.
- Unknown fields are rejected by the parking contract models.

## Enums

| Enum | Values |
|---|---|
| SlotStatus | AVAILABLE, RESERVED, OCCUPIED |
| ReservationStatus | ACTIVE, CONFIRMED, EXPIRED, CANCELLED |
| ParkingSessionStatus | ACTIVE, COMPLETED, CANCELLED |
| MapNodeType | ENTRANCE, EXIT, CHECKPOINT, ELEVATOR, AISLE, SLOT |
| ActorType | USER, SIMULATOR, CAMERA, SYSTEM |
| ParkingEventType | VEHICLE_ENTERED, SLOT_RESERVED, RESERVATION_CANCELLED, RESERVATION_EXPIRED, VEHICLE_PARKED, VEHICLE_LEFT_SLOT, VEHICLE_EXITED |
| ErrorCode | INVALID_TRANSITION, SLOT_NOT_FOUND, ROUTE_NODE_NOT_FOUND, ROUTE_NOT_FOUND, ACTIVE_SESSION_NOT_FOUND, SLOT_NOT_AVAILABLE, ACTIVE_RESERVATION_EXISTS, USER_NOT_FOUND, VEHICLE_NOT_FOUND, RESERVATION_NOT_FOUND, ACTIVE_RESERVATION_NOT_FOUND, RESERVATION_EXPIRED, ACTIVE_SESSION_EXISTS, SESSION_NOT_FOUND, LOCATION_NODE_NOT_FOUND, CURRENT_LOCATION_NOT_FOUND, INVALID_LOCATION_NODE_TYPE, AGENT_TOOL_UNAVAILABLE |

## Data schemas

The canonical Pydantic definitions live in src/models/schemas.py.

| Schema | Fields |
|---|---|
| User | id, display_name, current_node_id |
| Vehicle | id, user_id, plate_number, requires_charging |
| ParkingSlot | id, floor_id, zone_id, node_id, status, has_charger, is_accessible, version, occupied_by_vehicle_id |
| ParkingReservation | id, user_id, vehicle_id, slot_id, status, expires_at, created_at |
| ParkingSession | id, user_id, vehicle_id, slot_id, status, parked_at, completed_at |
| MapNode | id, floor_id, type, x, y |
| MapEdge | from_node, to_node, distance_m, bidirectional, enabled |
| RouteResult | path, distance_m, polyline |
| RecommendationRequest | user_id, start_node_id, zone_id, charging_required, accessible_required, near_elevator, limit |
| RecommendationCandidate | slot_id, score, distance_m, reasons |
| RecommendationResult | recommendations, parking_state_version |
| ParkingEvent | id, event_type, slot_id, actor_type, actor_id, old_status, new_status, created_at, metadata |

Nullable fields are User.current_node_id, ParkingSlot.occupied_by_vehicle_id,
ParkingSession.completed_at, RecommendationRequest.zone_id, and the event fields that may
not apply to a particular event:
slot_id, actor_id, old_status, and new_status. ParkingEvent.metadata defaults to an empty
object. MapEdge.bidirectional and MapEdge.enabled default to true.

### Parking slot contract

| Field | Type | Rules |
|---|---|---|
| id | string | Required; starts with F1- |
| floor_id | string | Required; F1 |
| zone_id | string | Required; A, B, C, or D |
| node_id | string | Required; starts with F1- |
| status | SlotStatus | Required |
| has_charger | boolean | Required |
| is_accessible | boolean | Required |
| version | integer | Required; zero or greater |
| occupied_by_vehicle_id | string or null | Vehicle occupying the slot; null when no vehicle ownership is recorded |

`occupied_by_vehicle_id` is a Phase 1 contract refinement that exposes the nullable
ownership field required by the persistence model. Parking State Service remains responsible
for changing it atomically with slot state and the corresponding ParkingEvent.

### Reservation timing

ParkingReservation.created_at and ParkingReservation.expires_at use UTC ISO 8601 timestamps. The default TTL and transition rules are defined by ADR-001; the contract does not implement expiry behavior.

## Response envelopes

Response envelopes are defined once in src/models/common.py.

SuccessResponse[T] contains:

- success: true
- data: the typed response payload
- message: an optional human-readable message

ErrorResponse contains:

- success: false
- error.code: a stable ErrorCode
- error.message: a human-readable message
- error.request_id: the request identifier used for tracing
- error.details: optional structured details that must not contain secrets

HTTP status codes and stable error codes follow the implementation guide:

| HTTP | Error code |
|---:|---|
| 400 | INVALID_TRANSITION |
| 404 | SLOT_NOT_FOUND, ROUTE_NODE_NOT_FOUND, ROUTE_NOT_FOUND, ACTIVE_SESSION_NOT_FOUND |
| 409 | SLOT_NOT_AVAILABLE, ACTIVE_RESERVATION_EXISTS |
| 503 | AGENT_TOOL_UNAVAILABLE |

Voice transcription additionally uses:

| HTTP | Error code |
|---:|---|
| 400 | SPEECH_AUDIO_INVALID |
| 413 | SPEECH_AUDIO_TOO_LARGE |
| 422 | SPEECH_NO_TRANSCRIPT |
| 503 | SPEECH_TRANSCRIPTION_UNAVAILABLE |
| 504 | SPEECH_TRANSCRIPTION_TIMEOUT |

Phase 4 lifecycle endpoints additionally use:

| HTTP | Error code |
|---:|---|
| 404 | USER_NOT_FOUND, VEHICLE_NOT_FOUND, RESERVATION_NOT_FOUND, ACTIVE_RESERVATION_NOT_FOUND, SESSION_NOT_FOUND, LOCATION_NODE_NOT_FOUND, CURRENT_LOCATION_NOT_FOUND |
| 409 | RESERVATION_EXPIRED, ACTIVE_SESSION_EXISTS |
| 422 | INVALID_LOCATION_NODE_TYPE |

## Agent chat

### `POST /api/v1/agent/chat`

The Phase 5 Agent endpoint provides non-streaming, thread-aware chat. Request:

```json
{
  "thread_id": "THREAD-DEMO-001",
  "user_id": "USER-001",
  "vehicle_id": "VEHICLE-001",
  "message": "Tìm cho tôi một ô có sạc gần thang máy"
}
```

`vehicle_id` is nullable so the Agent can ask the user to select a vehicle. Empty or
whitespace-only `thread_id` and `message` values are rejected. Unknown fields are rejected.

Success response:

```json
{
  "success": true,
  "data": {
    "thread_id": "THREAD-DEMO-001",
    "message": "Tôi tìm thấy các ô phù hợp...",
    "intent": "RECOMMEND_SLOT",
    "selected_slot": null,
    "tool_names": ["recommend_parking_slot"]
  },
  "message": null
}
```

`tool_names` contains only validated tool names and exists for safe debugging. The response
never contains analysis, chain-of-thought, system prompts, API keys, raw model metadata, or
raw exceptions.

Thread checkpoints use the internal namespace `user_id:thread_id`. A public `thread_id` can
belong to only one user while its checkpoint is retained; reuse by another user returns HTTP
409 with `INVALID_TRANSITION`. Idle threads expire after `AGENT_THREAD_TTL_SECONDS` (one hour
by default). Expiry removes the owner, checkpoint, and idle lock entry before that public ID
can start a new isolated thread. Thread memory uses `InMemorySaver`, so it is development/MVP
memory only: it is lost on process restart and is not shared across multiple workers.

Agent timeout, missing LLM configuration, or unexpected Agent/tool failures return HTTP 503
with `AGENT_TOOL_UNAVAILABLE` in the standard `ErrorResponse` envelope and include the request
ID. This endpoint does not provide streaming, WebSocket, voice, or QR behavior.

## Speech transcription

### `POST /api/v1/speech/transcriptions`

Accepts a short raw audio body with `Content-Type` set to `audio/webm`, `audio/ogg`,
`audio/mp4`, `audio/mpeg`, or `audio/wav`. The default request-size limit is 2 MB. Audio is
held in memory only for the provider request and is not persisted by ParkSmart.

Success response:

```json
{
  "success": true,
  "data": { "text": "Tìm ô trống ở khu D" },
  "message": null
}
```

The server uses `SPEECH_TRANSCRIPTION_MODEL` (default `gpt-4o-mini-transcribe`) and the same
server-side `LLM_API_KEY` credential. The credential is never sent to the browser. The
transcript is returned to the editable composer and is not automatically submitted to the
Agent endpoint. Transcription uses a 60-second timeout and one retry for transient network,
rate-limit, or provider failures by default.
