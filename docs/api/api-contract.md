# ParkSmart AI API contract

## Status and scope

This document defines the current identifiers, enums, Pydantic data contracts, and response envelopes. It does not define ORM models, database migrations, repositories, transactions, or parking business logic.

Public beta enables Agent chat with persistent daily quota and bounded step budget. Speech
retains its API contract but is disabled by configuration, so callers receive
`SPEECH_DISABLED`. Demo and simulator mutations are disabled in production. See
[`../PUBLIC_BETA.md`](../PUBLIC_BETA.md) for the deployed feature matrix.

ADR-001 remains authoritative for the meaning and lifecycle of RESERVED.

## Shared conventions

- JSON field names use snake_case exactly as defined by the Pydantic models. No camelCase aliases are provided.
- Floor-scoped identifiers start with F1-, F2-, or F3-, for example F2-A01, F3-CP2, and F1-ELEVATOR.
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
| MapNodeType | ENTRANCE, EXIT, CHECKPOINT, ELEVATOR, RAMP, AISLE, SLOT |
| ActorType | USER, ADMIN, SIMULATOR, CAMERA, SYSTEM |
| ParkingEventType | VEHICLE_ENTERED, SLOT_RESERVED, RESERVATION_CANCELLED, RESERVATION_EXPIRED, VEHICLE_PARKED, VEHICLE_LEFT_SLOT, VEHICLE_EXITED |
| WrongParkingReportStatus | OPEN, RESOLVED |
| WrongParkingReason | WRONG_SLOT, CROSSED_LINE, BLOCKING_ACCESS, OCCUPYING_CHARGER, OTHER |
| SlotObservationStatus | PENDING, VERIFIED, REJECTED, EXPIRED |
| WrongParkingReportVerificationOutcome | PENDING, CONFIRMED, REJECTED, DUPLICATE, UNVERIFIABLE |
| RewardSourceType | ADJACENT_SLOT_OBSERVATION, WRONG_PARKING_REPORT |
| RewardTransactionStatus | PENDING, EARNED, CANCELLED |
| ErrorCode | Canonical values live in `src/models/schemas.py`; public feature availability codes include AGENT_DISABLED and SPEECH_DISABLED; contribution/report additions include OBSERVATION_NOT_FOUND, OBSERVATION_ALREADY_EXISTS, OBSERVATION_EXPIRED, INVALID_OBSERVATION_TRANSITION, OBSERVATION_VERSION_CONFLICT, REWARD_ALREADY_SETTLED, REPORT_REWARD_DUPLICATE and CONTRIBUTION_DAILY_LIMIT_REACHED |

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
| RecommendationRequest | user_id, start_node_id, floor_id, zone_id, charging_required, accessible_required, near_elevator, limit |
| RecommendationCandidate | slot_id, score, distance_m, reasons |
| RecommendationResult | recommendations, parking_state_version |
| ParkingEvent | id, event_type, slot_id, actor_type, actor_id, old_status, new_status, created_at, metadata |
| SlotObservation | id, observer_user_id, observer_session_id, slot_id, observed_status, verification_status, reward_points, observed_slot_version, created_at, expires_at, verified_at, verified_by, rejection_reason, version, reward_status |
| WrongParkingReport | id, reporter_user_id, slot_id, reason_code, status, observed_plate_number, description, evidence_storage_path, evidence_content_type, evidence_size_bytes, created_at, updated_at, resolved_at, resolved_by, resolution_note, verification_outcome, reward_points, reward_status, duplicate_candidate_of_id, version |
| RewardTransaction | id, user_id, source_type, source_reference, transaction_type, status, points, created_at, settled_at, metadata |
| RewardSummary | available_points, pending_points, verified_contributions, daily_pending_points, daily_earned_points, daily_limit_points |

Nullable fields include User.current_node_id, ParkingSlot.occupied_by_vehicle_id,
ParkingSession.completed_at, RecommendationRequest.floor_id, RecommendationRequest.zone_id,
the optional report evidence/resolution/reward fields, and the event fields that may not
apply to a particular event:
slot_id, actor_id, old_status, and new_status. ParkingEvent.metadata defaults to an empty
object. MapEdge.bidirectional and MapEdge.enabled default to true.

### Parking slot contract

| Field | Type | Rules |
|---|---|---|
| id | string | Required; starts with F1-, F2-, or F3- |
| floor_id | string | Required; F1, F2, or F3 |
| zone_id | string | Required; A, B, C, or D |
| node_id | string | Required; starts with the same floor prefix as id |
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
| 429 | AGENT_DAILY_LIMIT_REACHED |
| 503 | AGENT_DISABLED, AGENT_TOOL_UNAVAILABLE |

Voice transcription additionally uses:

| HTTP | Error code |
|---:|---|
| 400 | SPEECH_AUDIO_INVALID |
| 413 | SPEECH_AUDIO_TOO_LARGE |
| 422 | SPEECH_NO_TRANSCRIPT |
| 503 | SPEECH_DISABLED, SPEECH_TRANSCRIPTION_UNAVAILABLE |
| 504 | SPEECH_TRANSCRIPTION_TIMEOUT |

Wrong-parking report lifecycle additionally uses:

| HTTP | Error code |
|---:|---|
| 404 | REPORT_NOT_FOUND |
| 409 | REPORT_VERSION_CONFLICT, INVALID_REPORT_TRANSITION |

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
    "tool_names": ["recommend_parking_slot"],
    "current_location": "F1-ENTRANCE",
    "recommended_slot_ids": ["F1-C01", "F1-C02"],
    "route": null,
    "ui_actions": [
      {
        "id": "select-slot-F1-C01",
        "type": "SELECT_SLOT",
        "label": "Chọn ô C01",
        "payload": {"slot_id": "F1-C01"},
        "style": "primary",
        "requires_confirmation": false
      }
    ]
  },
  "message": null
}
```

`tool_names` contains only validated tool names and exists for safe debugging. The response
never contains analysis, chain-of-thought, system prompts, API keys, raw model metadata, or
raw exceptions.

`ui_actions` defaults to an empty list for backward compatibility and contains at most five
presentation actions. Its type allowlist is `SELECT_LOCATION`,
`SELECT_PARKING_PREFERENCE`, `SELECT_SLOT`, `RESERVE_AND_ROUTE`, `CONFIRM_PARKING`,
`FIND_VEHICLE`, `COMPLETE_SESSION`, `OPEN_WRONG_PARKING_REPORT`, and `CANCEL`.
The backend derives these actions deterministically from validated runtime/tool data. LLM
prose is never parsed into buttons, URLs or tool names, and the final business mutation is
still validated by its Core API.

For recommendations, the workflow forwards the selected/current floor as `floor_id`.
`recommend_parking_slot` treats it as a hard candidate filter, while `zone_id` remains
optional; asking for “tầng 1” therefore does not require a follow-up question about zone.

Thread checkpoints use the internal namespace `user_id:thread_id`. A public `thread_id` can
belong to only one user while its checkpoint is retained; reuse by another user returns HTTP
409 with `INVALID_TRANSITION`. Idle threads expire after `AGENT_THREAD_TTL_SECONDS` (one hour
by default). Expiry removes the owner, checkpoint, and idle lock entry before that public ID
can start a new isolated thread. Thread memory uses `InMemorySaver`, so it is development/MVP
memory only: it is lost on process restart and is not shared across multiple workers.

Agent timeout, missing LLM configuration, or unexpected Agent/tool failures return HTTP 503
with `AGENT_TOOL_UNAVAILABLE` in the standard `ErrorResponse` envelope and include the request
ID. This endpoint does not provide streaming, WebSocket, voice, or QR behavior.

When `AGENT_ENABLED=false`, the authentication dependency still applies, then the handler
returns HTTP 503 with `AGENT_DISABLED` before ownership/vehicle resolution or quota
consumption. No LLM client or LangGraph graph is created and no graph is invoked.

When `AGENT_DAILY_REQUEST_LIMIT` is greater than zero, each authenticated/trusted parking
user may invoke the Agent at most that many times per UTC day. A request is charged after
authentication, ownership and vehicle validation succeed and immediately before graph
invocation. Later provider timeout or tool failure does not refund the request. Exceeding the
limit returns HTTP 429 with `AGENT_DAILY_LIMIT_REACHED`, the standard error envelope,
`X-Request-ID`, and a positive integer `Retry-After` header counting seconds until the next
UTC day. `AGENT_DAILY_REQUEST_LIMIT=0` disables quota persistence. `AGENT_MAX_STEPS` controls
the per-request graph step budget and is constrained to 1–8.

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

When `SPEECH_ENABLED=false`, the endpoint returns HTTP 503 with `SPEECH_DISABLED` before
reading the request body or invoking the transcription provider.

## Wrong-parking reports

### `POST /api/v1/reports/wrong-parking`

Creates an `OPEN` report at version `0`. `reason_code` is required. `description` may be
null for the four standard reasons; `OTHER` requires at least five trimmed characters.
`observed_plate_number` is optional and normalized to uppercase. Creating a report never
changes `ParkingSlot.status`.

The endpoint accepts either JSON (no image) or `multipart/form-data`. Multipart uses the
same fields plus optional `evidence`. Evidence is never required; when supplied it must be
JPEG, PNG, WebP, HEIC or HEIF and must not exceed `REPORT_EVIDENCE_MAX_BYTES`. The backend
validates both the declared MIME type and the file signature, reads the upload with a bounded
stream, and returns HTTP 413 with `REPORT_EVIDENCE_TOO_LARGE` when the configured byte limit
is exceeded. Invalid, empty, spoofed or unsupported image content returns HTTP 400 with
`REPORT_EVIDENCE_INVALID`. The backend chooses the private Storage path. The response includes nullable `evidence_storage_path`,
`evidence_content_type` and `evidence_size_bytes`; it never exposes the service-role key.

`WRONG_PARKING_REPORT_DAILY_LIMIT=0` disables the submission quota. When it is greater than
zero, successful report creation atomically consumes one persistent quota unit per trusted
parking user and UTC day, including duplicate reports and reports that receive no reward.
Validation and Storage upload failures do not consume quota. An exhausted quota returns HTTP
429 with `REPORT_DAILY_LIMIT_REACHED`, a positive `Retry-After` value until the next UTC day,
the standard error envelope and `X-Request-ID`. A read-only preflight avoids known-unnecessary
uploads; the transaction-time atomic consume remains authoritative under races, and a race
loser's uploaded object is deleted.

### Admin lifecycle endpoints

All admin endpoints use `require_admin_or_demo`:

- `GET /api/v1/admin/reports?status=OPEN&slot_id=F1-D01&limit=20` lists reports,
  newest first. `status` and `slot_id` are optional; `limit` is 1–100.
- `GET /api/v1/admin/reports/{report_id}` returns one report.
- `GET /api/v1/admin/reports/{report_id}/evidence-url` returns a five-minute signed URL
  when the optional evidence exists.
- `PATCH /api/v1/admin/reports/{report_id}` accepts `status=RESOLVED`, required
  non-`PENDING` `verification_outcome`, optional `resolution_note`, and required
  `expected_version`.
- `POST /api/v1/admin/reports/{report_id}/reopen` requires `expected_version`.
- `DELETE /api/v1/admin/reports/{report_id}?expected_version=N` permanently removes the
  database row and returns `deleted_report_id` in `SuccessResponse`.
- `PATCH /api/v1/admin/parking/slots/{slot_id}/status` accepts `status`
  (`AVAILABLE|OCCUPIED`) and required `expected_version`. It rejects `RESERVED` slots and
  delegates the transition and event creation to Parking State Service.

Resolve records UTC `resolved_at`, the admin actor, trimmed note, and increments `version`.
Reopen clears resolution metadata and increments `version`. Re-resolving or re-reopening is
an invalid transition. Every mutation uses optimistic concurrency and a database transaction;
a stale `expected_version` returns `REPORT_VERSION_CONFLICT`.

## Adjacent-slot user observations

### `POST /api/v1/parking/slots/{slot_id}/observation`

An actively parked user may optionally report one physically adjacent slot as
`AVAILABLE` or `OCCUPIED`:

```json
{
  "user_id": "USER-001",
  "observed_status": "OCCUPIED",
  "expected_slot_version": 3
}
```

The backend requires an active parking session and independently derives the left/right
neighbours within the same floor, zone and five-slot row on F1/F2/F3. Non-adjacent targets,
`RESERVED` slots and stale versions are rejected. Submission creates a `PENDING`
`SlotObservation` and optional `PENDING` reward, but never changes the slot. Admin verification
is the only path that may call Parking State Service and write an event with source
`verified_user_observation`.

## Phase 13 contribution and reward APIs

Mọi response tiếp tục dùng `SuccessResponse`/`ErrorResponse` chuẩn.

- `POST /api/v1/parking/slots/{slot_id}/observation` nhận `user_id`,
  `observed_status` (`AVAILABLE|OCCUPIED`) và `expected_slot_version`; trả
  `SlotObservation`, không trả/cập nhật `ParkingSlot`.
- `GET /api/v1/contributions/users/{user_id}` trả lịch sử contribution hợp nhất;
  observation record có `observer_session_id` để client không hỏi lại cùng một ô
  trong cùng phiên đỗ (report trả `null`).
- `GET /api/v1/rewards/users/{user_id}/summary` trả available/pending/verified và
  daily totals authoritative. Các path user được tách để sau này chuyển sang `/me`.
- `GET /api/v1/rewards/configuration` cung cấp copy/UI reward values, tránh hard-code.
- `GET /api/v1/admin/slot-observations` hỗ trợ `status`, `floor_id`, `slot_id`,
  `user_id`, `limit`; detail dùng `GET /api/v1/admin/slot-observations/{id}`.
- `POST /api/v1/admin/slot-observations/{id}/verify` và `/reject` yêu cầu
  `expected_version`; reject nhận thêm `reason` tùy chọn.
- Report response thêm `verification_outcome`, `reward_points`, `reward_status`,
  `duplicate_candidate_of_id`. PATCH resolve bắt buộc `status=RESOLVED`, một outcome
  khác `PENDING`, `expected_version`, và `resolution_note` tùy chọn.

Reward còn `PENDING` không phải điểm khả dụng. Chỉ outcome `CONFIRMED` hoặc observation
`VERIFIED` chuyển sang `EARNED`; các outcome âm/không xác minh chuyển `CANCELLED`.

### Roadmap ngoài API contract hiện tại: đổi voucher

Các endpoint phía trên chỉ hỗ trợ contribution và tích lũy điểm. Public beta **không có**
endpoint redemption, reward debit, voucher catalog/record hoặc tích hợp pricing. Mức đổi
100/200/400 điểm lấy 15/30/60 phút đỗ xe là đề xuất cho sản phẩm thật, không phải contract
đang hoạt động và không được client/Agent tự suy đoán.

Trước khi thêm endpoint, team phải duyệt ADR, migration và contract cho idempotency,
ownership, atomic debit/issuance, voucher expiry/application/refund và audit. Xem
[đặc tả ParkSmart Points voucher](../PARKSMART_POINTS_VOUCHERS.md).

## Supabase authentication

- `GET /api/v1/auth/me` maps a verified Supabase bearer token to the backend-owned profile.
- `POST /api/v1/auth/onboarding` idempotently creates a regular user profile and linked
  `ParkingUser`; token metadata cannot grant admin role.
- `POST /api/v1/auth/vehicles` adds a vehicle owned by the authenticated parking user and
  assigns it as the default when no default exists.

Outside demo mode, user-scoped APIs require a bearer token and reject a `user_id` or
`vehicle_id` not owned by that identity. Admin APIs require `profiles.app_role=admin`.
The browser client stores the Supabase session in `sessionStorage` with the ParkSmart
storage key, so separate tabs may hold independent user and admin sessions. Duplicating a
tab may still copy its initial session because that is browser behavior.
