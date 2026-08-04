# 04 — API Contract

## 1. Quy ước chung

Base URL:

```text
/api/v1
```

Authentication:

```http
Authorization: Bearer <supabase_access_token>
```

Success response:

```json
{
  "success": true,
  "data": {},
  "message": "Operation completed."
}
```

Error response:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message.",
    "details": null
  }
}
```

## 2. Health check

### `GET /health`

Authentication: Không yêu cầu.

Response `200`:

```json
{
  "status": "ok",
  "environment": "development"
}
```

## 3. Database health check

### `GET /api/v1/health/database`

Authentication: Không yêu cầu trong môi trường development.

Response `200`:

```json
{
  "success": true,
  "data": {
    "database": "connected"
  },
  "message": "Database is available."
}
```

Response `503`:

```json
{
  "success": false,
  "error": {
    "code": "DATABASE_UNAVAILABLE",
    "message": "Database connection failed.",
    "details": null
  }
}
```

## 4. Current user

### `GET /api/v1/me`

Allowed roles:

* resident
* security
* admin

Authentication: Bắt buộc.

Response `200`:

```json
{
  "success": true,
  "data": {
    "id": "2d3d879a-d188-4fee-98de-b92d20ca4f8b",
    "email": "resident.demo@example.com",
    "full_name": "Resident Demo",
    "app_role": "resident"
  },
  "message": "Current user loaded."
}
```

Errors:

| HTTP | Code              | Meaning                             |
| ---: | ----------------- | ----------------------------------- |
|  401 | AUTH_REQUIRED     | Không có access token               |
|  401 | INVALID_TOKEN     | Token sai hoặc hết hạn              |
|  403 | PROFILE_NOT_FOUND | Auth user chưa có ParkSmart profile |

## 5. Agent chat

### `POST /api/v1/agent/chat`

Allowed roles:

* resident
* security
* admin

Authentication: Bắt buộc.

Request:

```json
{
  "conversation_id": null,
  "message": "Bãi B2 còn chỗ trống không?"
}
```

Validation:

* `message` không được rỗng.
* Độ dài tối đa 2.000 ký tự.
* `conversation_id` có thể null trong tin nhắn đầu tiên.

Response `200`:

```json
{
  "success": true,
  "data": {
    "conversation_id": "21bc74ee-6686-46f8-b18b-63192653e25c",
    "message": "Agent đã nhận yêu cầu kiểm tra chỗ trống.",
    "intent": "CHECK_SLOT",
    "action": "MOCK_RESPONSE",
    "data": null
  },
  "message": "Agent request processed."
}
```

Errors:

| HTTP | Code                 | Meaning                        |
| ---: | -------------------- | ------------------------------ |
|  401 | AUTH_REQUIRED        | Người dùng chưa đăng nhập      |
|  401 | INVALID_TOKEN        | Token không hợp lệ             |
|  422 | VALIDATION_ERROR     | Request body không hợp lệ      |
|  500 | AGENT_INTERNAL_ERROR | Graph không xử lý được request |

## 6. API dự kiến cho MVP

### Vehicle

```http
GET    /api/v1/vehicles
POST   /api/v1/vehicles
PATCH  /api/v1/vehicles/{vehicle_id}
POST   /api/v1/vehicles/{vehicle_id}/deactivate
```

### Parking

```http
GET /api/v1/parking/areas
GET /api/v1/parking/areas/{area_id}/availability
GET /api/v1/parking/slots
```

### Reservation

```http
POST   /api/v1/reservations
GET    /api/v1/reservations/me
DELETE /api/v1/reservations/{reservation_id}
GET    /api/v1/reservations/{reservation_id}/guidance
```

### Guest registration

```http
POST /api/v1/guest-registrations
GET  /api/v1/guest-registrations/me
```

### Security

```http
GET  /api/v1/security/guest-registrations/today
POST /api/v1/security/guest-registrations/{guest_id}/check-in
POST /api/v1/security/guest-registrations/{guest_id}/check-out
```

### Approval

```http
GET  /api/v1/admin/approval-requests
GET  /api/v1/admin/approval-requests/{request_id}
POST /api/v1/admin/approval-requests/{request_id}/approve
POST /api/v1/admin/approval-requests/{request_id}/reject
```

### Simulator

```http
POST /api/v1/simulator/slots/{slot_id}/status
POST /api/v1/simulator/scenarios/rush-hour
POST /api/v1/simulator/scenarios/reset
```
