# ParkSmart AI — Các workflow public beta

Tài liệu này mô tả workflow đang bật trong public beta. Voice, Demo và Simulator bị tắt ở
production; các mô tả cũ về Voice/Simulator chỉ còn giá trị thiết kế tương lai. Xem
[PUBLIC_BETA.md](PUBLIC_BETA.md) cho feature matrix đầy đủ.

## 1. Mục tiêu hệ thống

ParkSmart AI hỗ trợ người dùng tìm và giữ ô đỗ, đi tới ô, lưu phiên đỗ, tìm lại xe và gửi
đóng góp cộng đồng trong bãi F1/F2/F3. AI Agent là một lớp hội thoại tùy chọn trên cùng Core
Services; recommendation, routing và state transition luôn deterministic/authoritative.

```mermaid
flowchart LR
    User["User/Admin"] --> UI["Next.js UI"]
    UI --> Gate{"Database ready?"}
    Gate -->|"No"| Wake["Cold-start notice + bounded retry"]
    Wake --> Gate
    Gate -->|"Yes"| Auth["Supabase Auth + ParkSmart profile"]
    Auth --> API["FastAPI boundary"]
    API --> Core["Core Services"]
    API --> Agent["LangGraph Agent"]
    Agent --> Tools["Allowlisted tools"]
    Tools --> Core
    Core --> DB[("Supabase PostgreSQL")]
```

## 2. Khởi động và xác thực

```mermaid
sequenceDiagram
    actor User
    participant UI as Vercel Next.js
    participant API as Render FastAPI
    participant DB as Supabase PostgreSQL
    participant Auth as Supabase Auth

    User->>UI: Mở ứng dụng
    UI->>API: GET /api/v1/health/database
    API->>DB: SELECT readiness
    DB-->>API: connected
    API-->>UI: 200
    UI->>Auth: Khởi tạo session theo tab
    User->>Auth: Sign up / sign in
    Auth-->>UI: Session/JWT
    UI->>API: GET /auth/me hoặc POST /auth/onboarding
    API->>DB: Resolve profile, role và parking identity
    DB-->>API: Authoritative profile
    API-->>UI: User/Admin session
```

Readiness gate dừng retry sau khi ready và không phải keep-alive. Role từ token metadata
không được tin cậy; backend luôn lấy `profiles.app_role` từ database.

## 3. Tìm, giữ và đi tới ô đỗ

```mermaid
flowchart TD
    Start["User chọn vị trí/tầng/nhu cầu"] --> Validate["Backend xác minh identity + vehicle"]
    Validate --> Recommend["Hard filters + deterministic scoring"]
    Recommend --> Candidate["Canonical AVAILABLE slot"]
    Candidate --> Confirm{"User xác nhận giữ?"}
    Confirm -->|"No"| Stop["Không mutation"]
    Confirm -->|"Yes"| Reserve["Transaction: AVAILABLE → RESERVED"]
    Reserve --> Event["ParkingEvent + reservation TTL"]
    Event --> Route["Graph routing từ vị trí tới slot"]
    Route --> UI["Map + turn-by-turn presentation"]
```

LLM không chọn slot hoặc tạo polyline. Frontend có thể khởi phát cùng workflow bằng thao tác
UI hoặc Agent chat, nhưng mutation vẫn đi qua REST/Core API có version/ownership checks.

## 4. Xác nhận đỗ và tìm lại xe

```mermaid
flowchart LR
    Arrive["User xác nhận đã tới"] --> Location["Cập nhật canonical location"]
    Location --> Refresh["Refetch version mới nhất"]
    Refresh --> Park["RESERVED → OCCUPIED"]
    Park --> Session["Tạo ParkingSession ACTIVE"]
    Session --> Later["User cập nhật checkpoint"]
    Later --> Find["Tra active session"]
    Find --> Route["Graph route checkpoint → parked slot"]
    Route --> Display["Hiển thị đường tìm xe"]
```

Parking Session là nguồn sự thật cho vị trí xe. Hệ thống không suy đoán vị trí từ hội thoại,
GPS hoặc browser storage.

## 5. Agent chat có quota

```mermaid
flowchart TD
    Message["Authenticated message"] --> Enabled{"AGENT_ENABLED?"}
    Enabled -->|"No"| Disabled["503 AGENT_DISABLED"]
    Enabled -->|"Yes"| Identity["Validate trusted user/vehicle"]
    Identity --> Quota{"Daily quota còn?"}
    Quota -->|"No"| Limited["429 AGENT_DAILY_LIMIT_REACHED"]
    Quota -->|"Yes"| Charge["Persist usage theo UTC"]
    Charge --> Graph["LangGraph, tối đa 4 bước"]
    Graph --> Tool["Allowlisted Core tool"]
    Tool --> Response["Safe response + verified UI actions"]
```

Public beta cho tối đa 5 request Agent/user/ngày UTC. Request đã charge vẫn tính khi LLM,
provider hoặc tool lỗi sau đó; không có retry tự động từ frontend khi quota đã hết.

## 6. Adjacent observation và ParkSmart Points

```mermaid
flowchart LR
    Active["Active parking session"] --> Select["Chọn slot kề trái/phải"]
    Select --> Pending["PENDING observation + reward reservation"]
    Pending --> Admin["Admin verify/reject"]
    Admin -->|"Verified + hợp lệ"| State["Parking State Service"]
    State --> Earned["Reward EARNED"]
    Admin -->|"Reject/expire/conflict"| Cancelled["Reward CANCELLED"]
```

Frontend chỉ gửi canonical slot/status/version. Backend xác minh adjacency, active session và
protected occupancy trước mutation. Ledger là nguồn authoritative cho Points.

## 7. Đổi điểm thành voucher — workflow mục tiêu, chưa triển khai

```mermaid
flowchart LR
    Earned["Điểm EARNED"] --> Select["Chọn voucher 15/30/60 phút"]
    Select --> Confirm["Xác nhận đổi điểm"]
    Confirm --> Atomic["Kiểm tra + trừ điểm + phát hành nguyên tử"]
    Atomic --> Voucher["Voucher cá nhân, hiệu lực 30 ngày"]
    Voucher --> Session["Áp dụng một lần cho một parking session"]
    Session --> Billing["Trừ phút miễn phí trước khi tính phí"]
```

Mức đề xuất là 100/200/400 điểm đổi 15/30/60 phút. Public beta hiện chưa có các bước này;
Agent không được khẳng định voucher đã khả dụng. Quy tắc đầy đủ và kiến trúc mục tiêu nằm tại
[PARKSMART_POINTS_VOUCHERS.md](PARKSMART_POINTS_VOUCHERS.md).

## 8. Báo cáo xe đỗ sai và ảnh bằng chứng

```mermaid
flowchart TD
    Draft["Chọn slot + reason"] --> Optional["Plate/description/one image optional"]
    Optional --> Confirm["Explicit submit"]
    Confirm --> Preflight["Auth, slot, quota và upload bounds"]
    Preflight --> Storage["Private Storage upload"]
    Storage --> Transaction["Consume quota + create OPEN report"]
    Transaction --> Admin["Admin list/detail"]
    Admin --> Signed["Short-lived signed evidence URL"]
    Admin --> Outcome["Resolve/reopen/hard-delete"]
```

Public beta giới hạn 5 report/user/ngày UTC. Ảnh tối đa 5.000.000 byte, MIME phải khớp
signature JPEG/PNG/WebP/HEIC/HEIF. Hard-delete xóa DB row và best-effort cleanup Storage;
cleanup failure được warning-log để operator theo dõi.

## 9. Workflow quản trị

Admin account chuyên dụng được provision theo
[ADMIN_PROVISIONING.md](ADMIN_PROVISIONING.md). Admin xem map/events, đổi slot status qua
Core Service, xác minh observations và xử lý report/evidence. Anonymous nhận 401, regular
user nhận 403; Demo/Simulator không tạo đường vòng quyền trong production.

## 10. Chức năng tương lai

```mermaid
flowchart LR
    Sensors["Camera/Sensors"] --> CV["Computer Vision/Event adapter"]
    CV --> Validate["Validated parking event"]
    Validate --> State["Parking State Service"]
    State --> DB[("Authoritative PostgreSQL")]
```

Camera/Computer Vision có thể thay nguồn sự kiện mô phỏng mà không đổi Core/Agent boundary.
Voice có thể bật lại sau khi hoàn thiện privacy, browser compatibility, cost limits và
production validation; hiện không thuộc public beta.
