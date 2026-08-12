# ParkSmart AI — Architecture

Tài liệu này mô tả ba góc nhìn kiến trúc chính của hệ thống ParkSmart AI:

1. **System Overview Diagram** — Bức tranh tổng thể của hệ thống.
2. **Agent Flow Diagram** — Luồng xử lý bên trong AI Agent.
3. **Deployment Diagram** — Cách các thành phần được triển khai.

## Nguyên tắc chính

- `Parking State Service` là source of truth cho trạng thái ô đỗ.
- Trạng thái ô đỗ trong MVP gồm `AVAILABLE`, `RESERVED` và `OCCUPIED`.
- Agent chỉ hiểu yêu cầu và gọi tools, không trực tiếp sửa database.
- Recommendation chọn ô bằng deterministic scoring, không để LLM tự chọn.
- Routing sử dụng parking graph với A* hoặc Dijkstra.
- Parking Simulator mô phỏng xe khác trong MVP.

---

## 1. System Overview Diagram

Sơ đồ tổng quan cho thấy cách người dùng, Backend, AI Agent, các dịch vụ nghiệp vụ và database kết nối với nhau.

```mermaid
graph TB
    subgraph Client["Frontend"]
        UI[Web / Mobile UI]
        Voice[Voice Input / Output]
    end

    subgraph Backend["Backend API"]
        API[FastAPI]
        State[Parking State Service]
        Recommend[Recommendation Service]
        Routing[Routing Service]
        Session[Parking Session Service]
        Simulator[Parking Simulator]
    end

    subgraph Agent["AI Agent"]
        Router[Intent Router]
        Tools[Agent Tools]
        Memory[Conversation Memory]
        LLM[LLM Provider]
    end

    subgraph Data["Data Layer"]
        DB[(Parking Database)]
        Map[(Parking Map Graph)]
    end

    UI --> API
    Voice --> API

    API --> Router
    Router --> Tools
    Router --> Memory
    Router --> LLM

    Tools --> State
    Tools --> Recommend
    Tools --> Routing
    Tools --> Session

    Recommend --> State
    Routing --> Map
    State --> DB
    Session --> DB

    Simulator --> State
```

### Vai trò các tầng

**Frontend** nhận text hoặc voice từ người dùng, cho phép chọn ID vị trí và hiển thị kết quả.

**Backend API** xử lý business logic, quản lý trạng thái bãi xe, recommendation, routing và parking session.

**AI Agent** hiểu yêu cầu, xác định intent và gọi Agent Tools phù hợp.

**Data Layer** lưu trạng thái ô đỗ, thông tin phiên đỗ xe và parking map graph.

### Trạng thái ô đỗ

- `AVAILABLE`: ô đang trống và có thể được đề xuất hoặc giữ chỗ.
- `RESERVED`: ô đang được giữ tạm thời cho một yêu cầu đã xác nhận; ô này không được đề xuất cho người khác.
- `OCCUPIED`: xe đã đỗ thực tế tại ô.

`RESERVED` trong MVP là cơ chế giữ ô có thời hạn, không phải chức năng đặt chỗ và thanh toán online hoàn chỉnh. Parking State Service chịu trách nhiệm kiểm tra chủ thể giữ chỗ, thời hạn và mọi chuyển trạng thái.

```mermaid
stateDiagram-v2
    [*] --> AVAILABLE
    AVAILABLE --> RESERVED: Xác nhận giữ ô
    AVAILABLE --> OCCUPIED: Xe mô phỏng đỗ trực tiếp
    RESERVED --> OCCUPIED: Xác nhận đã đỗ hợp lệ
    RESERVED --> AVAILABLE: Hủy hoặc hết thời hạn
    OCCUPIED --> AVAILABLE: Xe rời ô
```

---

## 2. Agent Flow Diagram

Sơ đồ mô tả các node, điều kiện rẽ nhánh và vòng lặp chính trong quá trình Agent xử lý yêu cầu.

```mermaid
graph TD
    START([User Input]) --> Understand[Understand Request]
    Understand --> CheckInfo{Enough Information?}

    CheckInfo -->|No| Ask[Ask for Missing Information]
    Ask --> START

    CheckInfo -->|Yes| Router[Intent Router]

    Router -->|Find Slot| Recommend[Recommendation Tool]
    Router -->|Reserve Slot| Reserve[Reservation Tool]
    Router -->|Get Directions| Route[Routing Tool]
    Router -->|Save Parking| Save[Parking Session Tool]
    Router -->|Find Vehicle| Find[Find Vehicle Tool]
    Router -->|Check Status| Status[Parking State Tool]

    Recommend --> Evaluate[Evaluate Tool Result]
    Reserve --> Evaluate
    Route --> Evaluate
    Save --> Evaluate
    Find --> Evaluate
    Status --> Evaluate

    Evaluate --> Success{Tool Successful?}
    Success -->|No| Error[Return Safe Error]
    Success -->|Yes| More{Need Another Tool?}

    More -->|Yes| Router
    More -->|No| Generate[Generate Response]

    Generate --> OUTPUT([Final Answer])
    Error --> OUTPUT
```

### Ví dụ các vòng lặp

- Nếu thiếu vị trí, mã ô hoặc thông tin xe, Agent hỏi lại người dùng rồi xử lý lại input.
- Nếu cần nhiều tool, Agent quay lại `Intent Router` để chọn bước tiếp theo.
- Nếu tool thất bại, Agent trả lỗi an toàn và không tự tạo dữ liệu thay thế.

### Ví dụ luồng tìm ô

```text
User Input
→ Intent Router
→ Recommendation Tool
→ Parking State Service
→ Deterministic Scoring
→ Final Answer
```

### Ví dụ luồng tìm lại xe

```text
User Input
→ Intent Router
→ Parking Session Tool
→ Routing Tool
→ Final Answer
```

---

## 3. Deployment Diagram

Sơ đồ minh họa cách triển khai MVP bằng Docker Compose trên một server.

```mermaid
graph LR
    User((User)) --> Internet((Internet))

    subgraph Server["Docker Compose Server"]
        subgraph FrontendContainer["Frontend Container"]
            Web[Web Application]
        end

        subgraph BackendContainer["Backend Container"]
            API[FastAPI Server]
            Services[Parking Services]
        end

        subgraph AgentContainer["Agent Container"]
            Agent[LangGraph Agent]
            Tools[Agent Tools]
        end

        subgraph SimulatorContainer["Simulator Container"]
            Simulator[Parking Simulator]
        end

        subgraph DatabaseContainer["Database Container"]
            DB[(PostgreSQL)]
        end
    end

    subgraph External["External Services"]
        LLM[LLM API]
        STT[Speech-to-Text API]
        TTS[Text-to-Speech API]
    end

    Internet --> Web
    Web --> API
    API --> Agent
    Agent --> Tools
    Tools --> Services
    Services --> DB
    Simulator --> Services

    Agent --> LLM
    API --> STT
    API --> TTS
```

### Thành phần triển khai

| Container | Chức năng |
|---|---|
| Frontend Container | Chạy giao diện web hoặc mobile web |
| Backend Container | Chạy FastAPI và các parking services |
| Agent Container | Chạy LangGraph Agent và Agent Tools |
| Simulator Container | Mô phỏng xe vào, đỗ và rời bãi |
| Database Container | Lưu dữ liệu bằng PostgreSQL |

### External dependencies

- **LLM API** dùng để Agent hiểu ngôn ngữ và lựa chọn tool.
- **Speech-to-Text API** chuyển giọng nói thành văn bản.
- **Text-to-Speech API** chuyển câu trả lời thành giọng nói.

Trong production, `Parking Simulator` có thể được thay bằng luồng:

```text
Camera → Computer Vision → Parking State Service
```

Các thành phần Agent, Recommendation, Routing và Parking Session không cần thay đổi lớn khi thay nguồn dữ liệu này.

---

## Architecture Summary

```text
Frontend
→ Backend API
→ AI Agent
→ Agent Tools
→ Parking Services
→ Database
```

AI Agent chịu trách nhiệm xử lý ngôn ngữ và điều phối. Các business services chịu trách nhiệm kiểm tra, quyết định và cập nhật dữ liệu nghiệp vụ.
