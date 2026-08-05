# ParkSmart AI Architecture Diagram

```mermaid
flowchart TD
    USER[User] --> FE[Next.js Frontend]

    FE -->|Login| AUTH[Supabase Auth]
    AUTH -->|Access Token| FE

    FE -->|REST API + Bearer Token| API[FastAPI API]
    FE <-->|Realtime Subscription| RT[Supabase Realtime]

    API --> AUTHZ[Authentication and Authorization]
    AUTHZ --> SERVICES[Business Services]

    API --> AGENT[LangGraph Agent]
    AGENT --> NODES[Agent Nodes]
    NODES --> TOOLS[Agent Tools]
    TOOLS --> SERVICES

    SERVICES --> RULES[Rule Engine]
    RULES --> DB[(PostgreSQL)]

    SERVICES --> SLOT[SlotProvider]
    SLOT --> SIM[Slot Simulator]

    AGENT --> RAG[RAG Service]
    RAG --> VECTOR[(pgvector)]

    SERVICES --> NOTIFY[Notification Service]
    SERVICES --> AUDIT[Audit Service]

    DB --> RT
```

## Luồng API

```mermaid
sequenceDiagram
    actor User
    participant FE as Next.js
    participant API as FastAPI
    participant Service
    participant DB as PostgreSQL

    User->>FE: Thực hiện thao tác
    FE->>API: Request + Bearer token
    API->>API: Xác thực và phân quyền
    API->>Service: Gọi nghiệp vụ
    Service->>DB: Transaction/query
    DB-->>Service: Kết quả
    Service-->>API: Structured result
    API-->>FE: API response
    FE-->>User: Hiển thị kết quả
```

## Luồng Agent

```mermaid
sequenceDiagram
    actor User
    participant FE as Next.js
    participant API as FastAPI
    participant Graph as LangGraph
    participant Tool as Agent Tool
    participant Service
    participant DB as PostgreSQL/RAG

    User->>FE: Gửi câu hỏi
    FE->>API: POST /agent/chat
    API->>Graph: Message + trusted user context
    Graph->>Graph: Classify intent
    Graph->>Tool: Execute tool
    Tool->>Service: Gọi business service
    Service->>DB: Query hoặc transaction
    DB-->>Service: Result
    Service-->>Tool: Structured result
    Tool-->>Graph: Tool result
    Graph-->>API: Agent response
    API-->>FE: Response
    FE-->>User: Hiển thị câu trả lời
```
## Deployment Diagram chi tiết hơn

```mermaid
flowchart TB
    subgraph Internet
        USER[User Browser]
    end

    subgraph Vercel["Vercel Hosting"]
        FE["Next.js App"]
    end

    subgraph Railway["Railway Deployment"]
        API["FastAPI Container"]
    end

    subgraph Supabase["Supabase Platform"]
        AUTH["Auth Service"]
        DB["PostgreSQL Database"]
        VEC["pgvector Extension"]
        REALTIME["Realtime Service"]
    end

    subgraph External["External Dependencies"]
        OPENAI["OpenAI API"]
    end

    subgraph DemoTools["Demo/Internal Services"]
        SIM["Slot Simulator"]
    end

    USER -->|HTTPS| FE
    FE -->|Bearer Token + REST| API
    FE -->|Auth UI / Session| AUTH
    FE <-->|Realtime WebSocket / Subscription| REALTIME

    API -->|JWT verification / user info| AUTH
    API -->|SQL queries| DB
    DB --> VEC
    API -->|Embedding / Chat completion| OPENAI
    API -->|Slot status sync| SIM

    REALTIME --> DB