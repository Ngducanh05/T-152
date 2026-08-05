# ParkSmart AI Architecture Diagrams

- **Project:** ParkSmart AI – Agent Quản lý và Điều phối Gửi xe Thông minh
- **Architecture style:** Modular Monolith
- **Backend:** FastAPI + LangGraph
- **Frontend:** Next.js
- **Database and Auth:** Supabase PostgreSQL, pgvector, Auth, Realtime
- **Deployment:** Vercel + Railway + Supabase Cloud

Tài liệu này mô tả ba góc nhìn kiến trúc chính của hệ thống:

1. **System Overview Diagram** – Tổng quan các thành phần và quan hệ giữa chúng.
2. **Agent Flow Diagram** – Luồng xử lý một yêu cầu gửi tới AI Agent.
3. **Deployment Diagram** – Cách hệ thống được triển khai, kết nối mạng và sử dụng dịch vụ bên ngoài.

---

## 1. System Overview Diagram

Sơ đồ này thể hiện các actor, frontend, backend, Agent, business services, database, realtime và các dịch vụ bên ngoài của ParkSmart AI.

```mermaid
flowchart TD
    subgraph Actors["Người dùng"]
        RESIDENT["Cư dân"]
        SECURITY["Bảo vệ"]
        ADMIN["Ban quản lý"]
    end

    subgraph Frontend["Frontend Layer"]
        FE["Next.js Web Application"]
        UI_RESIDENT["Resident Dashboard"]
        UI_SECURITY["Security Dashboard"]
        UI_ADMIN["Admin Dashboard"]
        UI_AGENT["Agent Chat UI"]
        UI_MAP["Parking Map"]
    end

    subgraph Backend["FastAPI Backend"]
        API["REST API Routes"]
        AUTHZ["Authentication and Authorization"]

        subgraph AgentLayer["LangGraph Agent"]
            GRAPH["State Graph"]
            NODES["Agent Nodes"]
            TOOLS["Agent Tools"]
        end

        subgraph ServiceLayer["Business Service Layer"]
            VEHICLE["Vehicle Service"]
            PARKING["Parking Service"]
            RESERVATION["Reservation Service"]
            GUEST["Guest Service"]
            APPROVAL["Approval Service"]
            NOTIFY["Notification Service"]
            AUDIT["Audit Service"]
            RULES["Rule Engine"]
            SLOT_PROVIDER["SlotProvider"]
            RAG["RAG Service"]
        end
    end

    subgraph Supabase["Supabase Platform"]
        AUTH["Supabase Auth"]
        DB[("PostgreSQL")]
        VECTOR[("pgvector")]
        RT["Supabase Realtime"]
    end

    subgraph External["External Dependencies"]
        LLM["OpenAI GPT-4o-mini"]
        SIM["Slot Simulator"]
    end

    RESIDENT --> FE
    SECURITY --> FE
    ADMIN --> FE

    FE --> UI_RESIDENT
    FE --> UI_SECURITY
    FE --> UI_ADMIN
    FE --> UI_AGENT
    FE --> UI_MAP

    FE -->|"Đăng nhập"| AUTH
    AUTH -->|"Access token"| FE

    FE -->|"HTTPS REST + Bearer token"| API
    FE <-->|"Realtime subscription"| RT

    API --> AUTHZ
    AUTHZ --> VEHICLE
    AUTHZ --> PARKING
    AUTHZ --> RESERVATION
    AUTHZ --> GUEST
    AUTHZ --> APPROVAL
    AUTHZ --> GRAPH

    GRAPH --> NODES
    NODES --> TOOLS
    TOOLS --> VEHICLE
    TOOLS --> PARKING
    TOOLS --> RESERVATION
    TOOLS --> GUEST
    TOOLS --> APPROVAL
    TOOLS --> RAG

    VEHICLE --> RULES
    PARKING --> RULES
    RESERVATION --> RULES
    GUEST --> RULES
    APPROVAL --> RULES

    VEHICLE --> DB
    PARKING --> DB
    RESERVATION --> DB
    GUEST --> DB
    APPROVAL --> DB
    NOTIFY --> DB
    AUDIT --> DB

    PARKING --> SLOT_PROVIDER
    SLOT_PROVIDER --> SIM

    RAG --> VECTOR
    RAG --> LLM
    GRAPH --> LLM

    DB --> RT
    DB --- VECTOR

    APPROVAL --> NOTIFY
    VEHICLE --> AUDIT
    RESERVATION --> AUDIT
    GUEST --> AUDIT
    APPROVAL --> AUDIT
```

### Nguyên tắc kiến trúc

- Frontend không truy cập trực tiếp dữ liệu nghiệp vụ để thực hiện thao tác ghi.
- FastAPI chịu trách nhiệm xác thực, phân quyền và điều phối request.
- Business logic nằm trong service layer, không nằm trong route hoặc Agent tool.
- Agent tool gọi service thay vì truy cập database trực tiếp.
- PostgreSQL là nguồn sự thật cho dữ liệu nghiệp vụ.
- pgvector chỉ lưu embedding của tài liệu nội quy và kiến thức chung.
- Dữ liệu slot thời gian thực được lấy qua `SlotProvider`, không lấy từ RAG.
- Agent không tự phê duyệt yêu cầu vượt định mức.

---

## 2. Agent Flow Diagram

Sơ đồ này mô tả luồng xử lý khi người dùng gửi yêu cầu bằng ngôn ngữ tự nhiên tới ParkSmart AI Agent.

```mermaid
sequenceDiagram
    autonumber

    actor User as Người dùng
    participant FE as Next.js Frontend
    participant API as FastAPI API
    participant Auth as Auth Service
    participant Graph as LangGraph
    participant Intent as Intent Node
    participant Tool as Agent Tool
    participant Service as Business Service
    participant Rule as Rule Engine
    participant DB as PostgreSQL
    participant RAG as RAG Service
    participant LLM as GPT-4o-mini

    User->>FE: Nhập yêu cầu bằng ngôn ngữ tự nhiên
    FE->>API: POST /api/v1/agent/chat + Bearer token

    API->>Auth: Xác minh access token
    Auth-->>API: user_id + app_role đáng tin cậy

    API->>Graph: message + user context
    Graph->>Intent: Phân loại intent
    Intent->>LLM: Structured intent classification
    LLM-->>Intent: Intent + extracted entities
    Intent-->>Graph: Cập nhật Agent state

    alt Câu hỏi về nội quy hoặc chính sách
        Graph->>RAG: Tìm knowledge chunks phù hợp
        RAG->>DB: Vector similarity search bằng pgvector
        DB-->>RAG: Relevant chunks + metadata
        RAG->>LLM: Câu hỏi + retrieved context
        LLM-->>RAG: Câu trả lời dựa trên context
        RAG-->>Graph: Answer + source metadata

    else Yêu cầu nghiệp vụ
        Graph->>Tool: Chọn tool phù hợp
        Tool->>Service: Gọi business service
        Service->>Rule: Kiểm tra business rules
        Rule-->>Service: Allowed / rejected / approval required

        alt Yêu cầu hợp lệ
            Service->>DB: Query hoặc transaction
            DB-->>Service: Kết quả nghiệp vụ
            Service-->>Tool: success=true + structured data
            Tool-->>Graph: Tool result

        else Cần Human-in-the-Loop
            Service->>DB: Tạo vehicle pending và approval request
            DB-->>Service: approval_request_id
            Service-->>Tool: approval_required
            Tool-->>Graph: Pending approval result

        else Không hợp lệ hoặc xảy ra lỗi
            Service-->>Tool: success=false + error code
            Tool-->>Graph: Structured error result
        end
    end

    Graph->>LLM: Tạo câu trả lời cuối từ Agent state
    LLM-->>Graph: Final response
    Graph-->>API: intent + action + message + data
    API-->>FE: JSON response
    FE-->>User: Hiển thị kết quả
```

### Quy tắc Agent

- `user_id` và `app_role` phải được lấy từ backend sau khi xác minh token.
- LLM không được tự cung cấp hoặc thay đổi danh tính người dùng.
- Agent chỉ xác nhận thao tác thành công khi tool trả `success=true`.
- Agent không được biến lỗi tool thành thông báo thành công.
- Agent không truy vấn trực tiếp PostgreSQL.
- Agent không sử dụng RAG để trả lời trạng thái slot, reservation hoặc approval hiện tại.
- Yêu cầu đăng ký xe vượt định mức phải chuyển sang quy trình HITL.

---

## 3. Deployment Diagram

Sơ đồ này thể hiện cách ParkSmart AI được triển khai trên môi trường production, bao gồm client, hosting, container backend, database, networking và external dependencies.

```mermaid
flowchart TB
    subgraph Client["Client Environment"]
        BROWSER["Web Browser"]
    end

    subgraph Vercel["Vercel Cloud"]
        NEXT["Next.js Frontend"]
        EDGE["Vercel Edge Network / HTTPS"]
    end

    subgraph Railway["Railway Cloud"]
        subgraph BackendContainer["Docker Container"]
            FASTAPI["FastAPI Application"]
            LANGGRAPH["LangGraph Runtime"]
            SERVICES["Business Services"]
            SLOT_PROVIDER["SimulatedSlotProvider"]
        end
        RAILWAY_NET["Railway Internal Networking"]
        ENV["Railway Environment Variables"]
    end

    subgraph SupabaseCloud["Supabase Cloud"]
        SUPA_AUTH["Supabase Auth"]
        SUPA_DB[("PostgreSQL Database")]
        SUPA_VECTOR[("pgvector Extension")]
        SUPA_RT["Supabase Realtime"]
    end

    subgraph OpenAICloud["OpenAI Cloud"]
        OPENAI["GPT-4o-mini API"]
        EMBEDDING["Embedding API"]
    end

    subgraph CICD["CI/CD"]
        GITHUB["GitHub Repository"]
        ACTIONS["GitHub Actions"]
    end

    BROWSER -->|"HTTPS"| EDGE
    EDGE --> NEXT

    NEXT -->|"Supabase Auth requests"| SUPA_AUTH
    SUPA_AUTH -->|"JWT access token"| NEXT

    NEXT -->|"HTTPS REST API + Bearer token"| FASTAPI
    NEXT <-->|"WebSocket / Realtime subscription"| SUPA_RT

    FASTAPI --> RAILWAY_NET
    LANGGRAPH --> SERVICES
    FASTAPI --> LANGGRAPH
    FASTAPI --> SERVICES
    SERVICES --> SLOT_PROVIDER

    FASTAPI -->|"HTTPS: token verification"| SUPA_AUTH
    SERVICES -->|"TLS PostgreSQL connection"| SUPA_DB
    SERVICES -->|"Vector queries"| SUPA_VECTOR
    SUPA_DB --- SUPA_VECTOR
    SUPA_DB --> SUPA_RT

    LANGGRAPH -->|"HTTPS API"| OPENAI
    SERVICES -->|"HTTPS embedding request"| EMBEDDING

    ENV --> FASTAPI
    ENV --> LANGGRAPH
    ENV --> SERVICES

    GITHUB --> ACTIONS
    ACTIONS -->|"Build and test Docker image"| BackendContainer
    ACTIONS -->|"Deploy frontend"| Vercel
    ACTIONS -->|"Deploy backend container"| Railway
```

### Thành phần triển khai

| Thành phần | Nơi triển khai | Vai trò |
|---|---|---|
| Next.js Frontend | Vercel | Giao diện cho resident, security và admin |
| FastAPI Backend | Railway Docker container | REST API, Auth, services và Agent entry point |
| LangGraph Runtime | Cùng container FastAPI | Điều phối Agent nodes và tools |
| PostgreSQL | Supabase Cloud | Lưu dữ liệu nghiệp vụ |
| pgvector | Extension trong Supabase PostgreSQL | Lưu và truy vấn embedding tài liệu |
| Supabase Auth | Supabase Cloud | Đăng nhập và phát hành access token |
| Supabase Realtime | Supabase Cloud | Cập nhật slot, approval và notification |
| GPT-4o-mini | OpenAI Cloud | Intent classification và response generation |
| Embedding API | OpenAI Cloud | Sinh embedding cho dữ liệu RAG |
| GitHub Actions | GitHub Cloud | Lint, test, Docker build và hỗ trợ deployment |

### Networking và bảo mật

- Mọi kết nối từ browser tới Vercel, Railway, Supabase và OpenAI phải sử dụng HTTPS hoặc TLS.
- Frontend gửi Supabase access token trong `Authorization: Bearer <token>` khi gọi FastAPI.
- Secret như `OPENAI_API_KEY`, `DATABASE_URL` và `SUPABASE_SERVICE_ROLE_KEY` chỉ nằm trong Railway Environment Variables.
- Frontend chỉ được sử dụng public configuration như `NEXT_PUBLIC_SUPABASE_URL` và `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
- Backend container không expose trực tiếp PostgreSQL ra Internet.
- CORS của FastAPI chỉ cho phép domain frontend đã cấu hình.
- Slot Simulator được chạy bên trong backend container trong môi trường MVP.

---

## 4. Local Development Deployment

Trong môi trường local, nhóm sử dụng Docker Compose để chạy backend và PostgreSQL/pgvector.

```mermaid
flowchart LR
    DEV["Developer Browser"] -->|"http://localhost:3000"| LOCAL_FE["Next.js Dev Server"]
    LOCAL_FE -->|"http://localhost:8000"| LOCAL_API["FastAPI Container"]

    subgraph DockerCompose["Docker Compose Network"]
        LOCAL_API -->|"postgresql://database:5432"| LOCAL_DB[("PostgreSQL + pgvector Container")]
        LOCAL_API --> LOCAL_SIM["Slot Simulator"]
    end

    LOCAL_FE -->|"Auth requests"| DEV_AUTH["Supabase Auth Development Project"]
    LOCAL_API -->|"LLM requests"| DEV_LLM["OpenAI API"]
```

Lệnh chạy dự kiến:

```bash
docker compose up --build
```

Các cổng local:

| Service | URL/Port |
|---|---|
| Next.js | `http://localhost:3000` |
| FastAPI | `http://localhost:8000` |
| Swagger UI | `http://localhost:8000/docs` |
| PostgreSQL | `localhost:5432` |

---

## 5. Nguồn sự thật kiến trúc

Khi có xung đột giữa sơ đồ và implementation, thứ tự ưu tiên là:

1. Quyết định mới nhất của Leader đã được ghi trong issue hoặc tài liệu.
2. `docs/AI_PROJECT_CONTEXT.md`.
3. `docs/guide/02_system_architecture.md`.
4. `docs/guide/04_api_contract.md`.
5. File này.
6. Code đã merge vào nhánh `develop`.

Mọi thay đổi quan trọng về deployment, networking, external dependency hoặc luồng Agent phải cập nhật lại tài liệu này.
