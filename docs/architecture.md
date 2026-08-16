# ParkSmart AI — Architecture

Tài liệu này mô tả kiến trúc đang được triển khai của ParkSmart AI: hai giao
diện Next.js cho người dùng và quản trị viên, FastAPI chứa Agent cùng các dịch
vụ nghiệp vụ, PostgreSQL là nơi lưu trạng thái authoritative, và các dịch vụ
LLM/STT bên ngoài chỉ được gọi qua backend khi cần.

## Nguyên tắc chính

- `Parking State Service` là source of truth cho trạng thái ô đỗ.
- Trạng thái ô đỗ gồm `AVAILABLE`, `RESERVED` và `OCCUPIED`.
- Agent hiểu yêu cầu và gọi tools; Agent không sửa database trực tiếp.
- Recommendation dùng deterministic filtering/scoring, không để LLM tự chọn ô.
- Routing dùng parking graph; frontend chỉ vẽ route backend trả về.
- User UI và Admin UI dùng chung API contract và Core Services.
- Simulator mutation chỉ hoạt động trong demo mode hoặc với quyền admin.
- Voice là một kênh nhập/xuất; text cuối cùng vẫn đi qua Agent endpoint như chat.
- Không có QR trong MVP.

---

## 1. System Overview và component boundaries

```mermaid
flowchart TB
    subgraph Browser["Next.js frontend"]
        UserUI["User UI — /"]
        AdminUI["Admin UI — /admin"]
        Shared["Shared map, API client, types and polling"]
        WebSpeech["Browser Web Speech — STT/TTS"]
    end

    subgraph Backend["FastAPI backend process"]
        PublicAPI["Parking, location, reservation, routing and report APIs"]
        AgentAPI["POST /api/v1/agent/chat"]
        SpeechAPI["POST /api/v1/speech/transcriptions — fallback"]
        AdminAPI["Admin events and simulator APIs"]
        Agent["LangGraph Agent"]
        Tools["Agent Tools"]
        Core["Core business services"]
        Simulator["Simulator module"]
    end

    subgraph Data["Authoritative data"]
        DB[("PostgreSQL")]
        Map["Canonical parking graph"]
    end

    subgraph External["External providers"]
        LLM["LLM API"]
        STT["Speech-to-Text API"]
    end

    UserUI --> Shared
    AdminUI --> Shared
    WebSpeech --> UserUI
    Shared --> PublicAPI
    UserUI --> AgentAPI
    AdminUI --> AdminAPI
    UserUI -. "Web Speech unavailable" .-> SpeechAPI

    AgentAPI --> Agent
    Agent --> LLM
    Agent --> Tools
    Tools --> Core
    PublicAPI --> Core
    AdminAPI --> Core
    AdminAPI --> Simulator
    Simulator --> Core
    SpeechAPI --> STT

    Core --> DB
    Core --> Map
```

### Trách nhiệm của hai giao diện

| Giao diện | Trách nhiệm | Không được làm |
|---|---|---|
| User UI `/` | Xem bản đồ, xác nhận vị trí bằng ID, tìm/giữ ô, route, phiên đỗ xe, báo cáo xe đỗ sai, chat và voice | Reset demo, điều khiển simulator, hiển thị tool/thread hoặc tự sửa trạng thái |
| Admin UI `/admin` | KPI mật độ, mật độ theo khu, filter map, simulator controls, reports và parking events | Tự ghi database hoặc tính lại business transition ở frontend |

`/admin` dùng `CurrentUser.app_role` khi authentication được bật. Trong demo
mode, backend có thể cho phép trang vận hành mà không cần bearer token; giao
diện phải ghi rõ đây là `Admin Demo`, không phải bảo mật production.

### Trách nhiệm backend

- `src/api`: validation, authentication/authorization dependency, REST adapter,
  response envelope và request ID.
- `src/agents`: LangGraph orchestration và tool adapters.
- `src/core`: state transitions, recommendation, routing, reservation, parking
  session, location, simulator và wrong-parking report rules.
- PostgreSQL: slot state, reservations, sessions, users, vehicles, events và
  wrong-parking reports.

---

## 2. Data flow

### 2.1 User parking flow

```mermaid
sequenceDiagram
    actor User
    participant UI as User UI
    participant API as FastAPI
    participant Agent as LangGraph Agent
    participant Tools as Agent Tools
    participant Core as Core Services
    participant DB as PostgreSQL

    User->>UI: Text, voice hoặc thao tác UI
    opt Voice
        UI->>UI: SpeechRecognition tạo transcript
        User->>UI: Kiểm tra transcript rồi gửi
    end
    UI->>API: POST /api/v1/agent/chat
    API->>Agent: Message + trusted runtime context
    Agent->>Tools: Gọi tool phù hợp
    Tools->>Core: Gọi business service
    Core->>DB: Đọc hoặc mutation trong transaction
    DB-->>Core: Authoritative result
    Core-->>Tools: Structured result
    Tools-->>Agent: Safe tool output
    Agent-->>API: Natural-language response + structured UI effects
    API-->>UI: ChatResponse
    UI-->>User: Text, map/route update và optional TTS
```

Nếu Browser Speech Recognition không khả dụng, frontend có thể ghi âm và gửi
audio tới `/api/v1/speech/transcriptions`. Backend giữ API key STT; frontend
không gọi provider trực tiếp và không lưu raw audio sau request.

### 2.2 Admin operations flow

```mermaid
sequenceDiagram
    actor Admin
    participant UI as Admin UI
    participant API as FastAPI Admin/Simulator API
    participant Core as Simulator + Parking State
    participant DB as PostgreSQL
    participant UserUI as User UI polling

    Admin->>UI: Chọn park, leave, reset hoặc fixed scenario
    UI->>API: Validated mutation request
    API->>API: require_admin_or_demo
    API->>Core: Simulator action
    Core->>DB: Transaction + ParkingEvent
    DB-->>Core: Authoritative state
    Core-->>API: Structured result
    API-->>UI: Success/error envelope
    UI->>API: Refresh status, slots and events
    UserUI->>API: Poll current parking state
    API-->>UserUI: Updated authoritative state
```

Admin density is a current snapshot, calculated from `ParkingStatus.by_zone`:

```text
utilization = (RESERVED + OCCUPIED) / total * 100
```

Hệ thống chưa lưu occupancy snapshots theo thời gian, vì vậy không hiển thị
biểu đồ lịch sử hoặc dự đoán giả.

### 2.3 Wrong-parking report flow

```mermaid
flowchart LR
    User["User selects a canonical slot"] --> ReportAPI["POST /api/v1/reports/wrong-parking"]
    ReportAPI --> Validate["Validate user and slot"]
    Validate --> DB[("wrong_parking_reports")]
    DB --> AdminAPI["GET /api/v1/admin/reports"]
    AdminAPI --> AdminUI["Admin report list"]
```

---

## 3. Slot state machine

`RESERVED` là giữ ô có thời hạn, không phải booking/thanh toán thương mại.

```mermaid
stateDiagram-v2
    [*] --> AVAILABLE
    AVAILABLE --> RESERVED: User confirms reservation
    AVAILABLE --> OCCUPIED: Simulator parks directly
    RESERVED --> OCCUPIED: Valid parking confirmation
    RESERVED --> AVAILABLE: Cancel or expire
    OCCUPIED --> AVAILABLE: Vehicle leaves
```

Mọi transition quan trọng chạy trong transaction và tạo `ParkingEvent`. UI chỉ
cập nhật sau khi backend thành công rồi refresh authoritative state.

---

## 4. Agent flow

```mermaid
flowchart TD
    Start(["User message"]) --> Understand["Understand intent and entities"]
    Understand --> Enough{"Enough trusted information?"}
    Enough -->|No| Ask["Ask one focused question"]
    Ask --> Start
    Enough -->|Yes| Select["Select allowed tool"]
    Select --> Tool["Execute tool with runtime context"]
    Tool --> Result{"Tool successful?"}
    Result -->|No| SafeError["Return safe actionable error"]
    Result -->|Yes| More{"Need another tool?"}
    More -->|Yes| Select
    More -->|No| Respond["Generate response from tool data"]
    Respond --> End(["ChatResponse"])
    SafeError --> End
```

Agent không được:

- tự chọn slot ngoài kết quả Recommendation Service;
- tự tạo route;
- truyền `user_id`, `vehicle_id` hoặc `request_id` do model sinh;
- sửa database trực tiếp;
- bịa dữ liệu khi tool thất bại.

---

## 5. Deployment architecture hiện tại

`docker-compose.yml` hiện container hóa PostgreSQL và FastAPI backend. Agent và
Simulator chạy như module trong backend process. Frontend Next.js hiện được
chạy riêng bằng npm trong development; container frontend là bước deployment
chưa hoàn tất.

```mermaid
flowchart LR
    subgraph Compose["Docker Compose hiện tại"]
        API["FastAPI backend container"]
        DB[("PostgreSQL container")]
        API --> DB
    end

    Browser["Browser: User UI / Admin UI / Web Speech"] --> Next["Next.js dev or deployed frontend"]
    Next --> API
    API --> LLM["LLM provider"]
    API -. "STT fallback" .-> STT["Speech-to-Text provider"]
```

| Runtime | Nội dung |
|---|---|
| Browser | `/`, `/admin`, Browser Speech Recognition và `speechSynthesis` |
| Next.js | User/Admin rendering, API client và polling |
| Backend container | FastAPI, LangGraph Agent, tools, Core Services và Simulator module |
| Database container | PostgreSQL authoritative state và events/reports |
| External provider | LLM; STT chỉ khi browser fallback được dùng |

Production tương lai có thể thay Simulator bằng:

```text
Camera → Computer Vision → validated event → Parking State Service
```

Agent, recommendation, routing và parking-session boundaries không thay đổi khi
nguồn sự kiện được thay thế.

---

## 6. Architecture summary

```text
User UI / Admin UI
        ↓
FastAPI boundary
        ↓
Agent Tools hoặc REST adapters
        ↓
Core business services
        ↓
PostgreSQL + canonical parking graph
```

Frontend quyết định cách trình bày. Agent quyết định tool nào cần gọi. Chỉ Core
Services quyết định nghiệp vụ và chỉ PostgreSQL lưu trạng thái authoritative.
