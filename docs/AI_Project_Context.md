# AI PROJECT CONTEXT — PARKSMART AI

> Đây là tài liệu ngữ cảnh thống nhất dành cho toàn bộ thành viên và các AI Assistant tham gia dự án.
>
> Trước khi yêu cầu AI viết code, thiết kế API, xây dựng Agent, kiểm thử hoặc viết tài liệu, thành viên phải cung cấp nội dung file này cho AI.
>
> AI không được tự ý thay đổi phạm vi MVP, kiến trúc, công nghệ, API contract hoặc business rule nếu chưa có quyết định của Leader.

---

# 1. Thông tin dự án

## 1.1 Tên dự án

**ParkSmart AI – Agent Quản lý và Điều phối Gửi xe Thông minh**

## 1.2 Thời gian thực hiện

* Thời gian phát triển: **2 tuần**
* Số thành viên: **4 người**
* Mục tiêu: xây dựng một MVP có thể chạy, kiểm thử, deploy và demo được.

## 1.3 Thành viên và trách nhiệm

| Thành viên  | Trách nhiệm chính                                                       |
| ----------- | ----------------------------------------------------------------------- |
| Leader      | Kiến trúc, quản lý dự án, API contract, tích hợp, review, CI/CD, deploy |
| Đoàn        | Database, backend nghiệp vụ, authentication, rule engine                |
| Quang Thành | Next.js frontend, Supabase Auth, UI/UX, sơ đồ bãi xe, realtime          |
| Phú Thành   | LangGraph Agent, Agent tools, RAG, prompt, Agent evaluation             |

## 1.4 Thứ tự ưu tiên

1. Luồng nghiệp vụ chính phải chạy đúng.
2. Agent phải sử dụng tool, không tự bịa dữ liệu.
3. Các thành viên phải dễ tích hợp code.
4. Code đơn giản, rõ ràng, phù hợp thời gian hai tuần.
5. Các chức năng nhạy cảm phải được kiểm soát bằng rule và phân quyền.
6. Hệ thống phải có test và dữ liệu demo.
7. Không xây dựng kiến trúc phức tạp không cần thiết.

---

# 2. Bài toán cần giải quyết

Hầm gửi xe của doanh nghiệp bất động sản thường quá tải vào giờ cao điểm.

Các vấn đề chính:

* Cư dân không biết khu hoặc tầng nào còn chỗ.
* Khách vãng lai không rõ vị trí gửi xe phù hợp.
* Đăng ký thẻ xe và đổi xe còn thủ công.
* Cư dân có thể đăng ký vượt định mức xe của căn hộ.
* Ban quản lý phải xử lý nhiều yêu cầu thủ công.
* Trạng thái chỗ đỗ phải được cập nhật gần thời gian thực.
* Biển số và dữ liệu ra vào là dữ liệu nhạy cảm.
* Hệ thống phải hạn chế gian lận đăng ký và truy cập trái phép.

ParkSmart AI cung cấp AI Agent hỗ trợ:

* Quản lý phương tiện.
* Đăng ký phương tiện.
* Tra cứu chỗ trống.
* Đặt và hủy chỗ.
* Hướng dẫn tầng, khu và vị trí đỗ.
* Đăng ký xe khách.
* Kiểm tra trạng thái yêu cầu.
* Giải đáp nội quy gửi xe.
* Chuyển yêu cầu vượt định mức cho BQL phê duyệt.

---

# 3. Phạm vi MVP

## 3.1 Chức năng bắt buộc

### Authentication và phân quyền

Hệ thống có ba vai trò:

```text
resident
security
admin
```

Trong đó:

* `resident`: cư dân.
* `security`: bảo vệ.
* `admin`: Ban quản lý.

Yêu cầu:

* Đăng nhập bằng Supabase Auth.
* Frontend gửi Supabase access token đến FastAPI.
* FastAPI xác minh JWT.
* Backend xác định danh tính và quyền người dùng.
* Không chỉ kiểm tra quyền bằng cách ẩn nút trên frontend.
* Không tin tưởng `user_id` hoặc `role` do client gửi trong request body.

### Quản lý phương tiện

* Cư dân xem danh sách xe của mình.
* Cư dân đăng ký thêm xe.
* Cư dân cập nhật thông tin xe được phép thay đổi.
* Cư dân ngừng sử dụng một xe.
* Hệ thống kiểm tra biển số trùng.
* Xe vượt định mức phải chờ BQL duyệt.

### Quản lý chỗ đỗ

* Xem danh sách tầng và khu.
* Xem số slot còn trống.
* Xem trạng thái từng slot.
* Đặt chỗ.
* Hủy đặt chỗ.
* Hướng dẫn tầng, khu và mã slot.
* Ngăn hai người đặt cùng một slot.

### Xe khách

* Cư dân đăng ký xe khách.
* Cư dân khai báo thời gian xe khách có hiệu lực.
* Bảo vệ xem danh sách xe khách hợp lệ.
* Bảo vệ check-in và check-out.

### Human-in-the-Loop

Khi cư dân đăng ký xe vượt định mức:

1. Tạo phương tiện với trạng thái `pending`.
2. Tạo `approval_request`.
3. BQL xem yêu cầu.
4. BQL duyệt hoặc từ chối.
5. Hệ thống cập nhật phương tiện.
6. Hệ thống tạo notification cho cư dân.
7. Hệ thống ghi audit log.

Agent không được tự phê duyệt yêu cầu.

### AI Agent

Agent hỗ trợ tối thiểu các intent:

```text
CHECK_SLOT
RESERVE_SLOT
CANCEL_RESERVATION
REGISTER_VEHICLE
REGISTER_GUEST
CHECK_REQUEST_STATUS
POLICY_QUESTION
UNKNOWN
```

### RAG

RAG được dùng cho:

* Nội quy gửi xe.
* Quy trình đăng ký thẻ xe.
* Chính sách định mức.
* Quy định xe khách.
* Quy trình xử lý mất thẻ.
* Câu hỏi thường gặp.

RAG không được dùng để truy vấn dữ liệu realtime hoặc dữ liệu cá nhân.

### Realtime

Frontend cần cập nhật khi:

* Trạng thái slot thay đổi.
* Reservation được tạo hoặc hủy.
* Approval được duyệt hoặc từ chối.
* Notification mới được tạo.

---

# 4. Ngoài phạm vi MVP

Không triển khai trong hai tuần:

* Camera nhận diện biển số thật.
* Cảm biến vật lý.
* Điều khiển barrier.
* Thanh toán phí gửi xe.
* Ứng dụng mobile riêng.
* Bản đồ dẫn đường 3D.
* Computer vision phát hiện gian lận.
* Mô hình machine learning dự báo tải phức tạp.
* Tích hợp hệ thống quản lý tòa nhà thật.
* Kubernetes hoặc kiến trúc microservice.

Các chức năng này chỉ được trình bày dưới dạng roadmap.

---

# 5. Giả định dữ liệu slot

MVP chưa tích hợp camera hoặc cảm biến thật.

Trạng thái chỗ đỗ được cung cấp bởi **Slot Simulator**.

Simulator hỗ trợ:

* Chuyển slot thành `available`.
* Chuyển slot thành `reserved`.
* Chuyển slot thành `occupied`.
* Chuyển slot thành `maintenance`.
* Chạy kịch bản giờ cao điểm.
* Reset dữ liệu demo.

Các service và Agent không phụ thuộc trực tiếp vào simulator.

Cần sử dụng abstraction:

```python
from typing import Protocol
from uuid import UUID


class SlotProvider(Protocol):
    async def get_available_slots(
        self,
        parking_area_id: UUID,
        vehicle_type: str,
    ) -> list:
        ...

    async def update_slot_status(
        self,
        slot_id: UUID,
        status: str,
    ):
        ...
```

MVP sử dụng:

```text
SimulatedSlotProvider
```

Trong tương lai có thể thay bằng:

```text
SensorSlotProvider
CameraSlotProvider
ExternalAPISlotProvider
```

---

# 6. Tech stack thống nhất

## 6.1 Backend

* Python 3.11 hoặc phiên bản đã được nhóm thống nhất.
* FastAPI.
* Pydantic.
* Pydantic Settings.
* SQLAlchemy.
* Alembic.
* PostgreSQL.
* pgvector.
* pytest.

## 6.2 AI Agent

* GPT-4o-mini.
* LangGraph.
* Tool calling.
* Structured output.
* Retrieval-Augmented Generation.
* Rule-based validation.
* pgvector retrieval.

## 6.3 Frontend

* Next.js.
* TypeScript.
* App Router.
* Supabase Auth.
* Supabase Realtime.
* Sơ đồ bãi xe dạng grid 2D.

Frontend có thể được lưu trong repository riêng hoặc được bổ sung sau. Frontend phải tuân thủ API contract của FastAPI.

## 6.4 Authentication

* Supabase Auth.
* Supabase JWT.
* Role-based authorization tại backend.

## 6.5 Deployment

* Backend: Railway hoặc nền tảng chạy Docker tương thích.
* Frontend: Vercel.
* Database/Auth: Supabase.
* Local development: Docker Compose.

Không tự ý đổi sang:

* Django.
* Flask.
* NestJS.
* MongoDB.
* Firebase.
* Một Agent framework khác.
* Một vector database khác.

---

# 7. Cấu trúc repository chính thức

```text
parksmart-ai/
├── src/
│   ├── agents/
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes/
│   │   └── tools/
│   ├── api/
│   │   └── routes.py
│   ├── models/
│   ├── services/
│   ├── config.py
│   └── main.py
├── tests/
│   ├── test_agents/
│   └── test_api/
├── scripts/
│   ├── log_hook.py
│   ├── log_antigravity.py
│   ├── log_manual.py
│   ├── submit_log.py
│   └── setup_hooks.sh
├── .claude/
├── .codex/
├── .cursor/
├── .gemini/
├── .agents/
├── .ai-log/
├── docs/
│   ├── guide/
│   └── architecture_diagram.md
├── eval/
├── presentation/
├── .github/
│   ├── workflows/
│   └── hooks/
├── Dockerfile
├── docker-compose.yml
└── README_boilerplate.md
```

---

# 8. Quy định sử dụng từng thư mục

## 8.1 `src/agents/`

Chứa toàn bộ mã nguồn liên quan đến LangGraph Agent.

Không đặt:

* FastAPI route.
* SQLAlchemy model.
* Logic xác thực JWT.
* Business logic nghiệp vụ chính.
* Code frontend.

### `src/agents/state.py`

Chứa schema trạng thái của Agent.

Ví dụ:

```python
from typing import Any, TypedDict


class ParkingAgentState(TypedDict, total=False):
    messages: list
    user_id: str
    user_role: str

    intent: str | None

    vehicle_id: str | None
    parking_area_id: str | None
    reservation_id: str | None
    approval_request_id: str | None

    requires_approval: bool
    tool_result: dict[str, Any] | None
    error: str | None
```

Không đặt node implementation trong file này.

### `src/agents/graph.py`

Chịu trách nhiệm:

* Khởi tạo `StateGraph`.
* Đăng ký node.
* Định nghĩa edge.
* Định nghĩa conditional edge.
* Compile graph.
* Export Agent graph để API gọi.

Không đặt business rule chi tiết trong `graph.py`.

### `src/agents/nodes/`

Mỗi node nên có một trách nhiệm rõ ràng.

Gợi ý:

```text
src/agents/nodes/
├── load_context.py
├── classify_intent.py
├── execute_tool.py
├── retrieve_policy.py
├── generate_response.py
└── handle_error.py
```

Node được phép:

* Đọc Agent state.
* Gọi tool.
* Gọi service AI.
* Cập nhật Agent state.

Node không được:

* Viết SQL trực tiếp.
* Tự quyết định quyền của người dùng.
* Tự bỏ qua business rule.
* Tự tạo dữ liệu slot giả.

### `src/agents/tools/`

Chứa tool mà LangGraph hoặc LLM được phép gọi.

Gợi ý:

```text
src/agents/tools/
├── vehicle_tools.py
├── parking_tools.py
├── reservation_tools.py
├── guest_tools.py
├── approval_tools.py
└── policy_tools.py
```

Mỗi tool phải:

* Có input schema rõ ràng.
* Có output có cấu trúc.
* Lấy user context từ runtime.
* Gọi hàm trong `src/services/`.
* Không truy cập database trực tiếp.
* Không lặp lại business logic.
* Không trả dữ liệu không cần thiết cho LLM.

---

## 8.2 `src/api/`

Chứa FastAPI router và API dependencies.

Cấu trúc ban đầu quy định:

```text
src/api/
└── routes.py
```

Trong MVP nhỏ, các endpoint có thể bắt đầu trong `routes.py`.

Khi file quá lớn, được phép tách thêm:

```text
src/api/
├── routes.py
├── dependencies.py
└── routers/
    ├── vehicles.py
    ├── parking.py
    ├── reservations.py
    ├── guests.py
    ├── approvals.py
    └── agent.py
```

Chỉ tách khi cần thiết và phải giữ `routes.py` làm router tổng.

API layer chịu trách nhiệm:

* Nhận request.
* Validate request bằng Pydantic.
* Lấy authenticated user.
* Kiểm tra role ở mức endpoint.
* Gọi service.
* Trả response.

API layer không được chứa:

* Business logic dài.
* SQL query trực tiếp.
* Logic LangGraph chi tiết.
* Quyết định định mức xe.
* Logic transaction đặt slot.

---

## 8.3 `src/models/`

Chứa **Pydantic schemas** dùng cho:

* API request.
* API response.
* Tool input.
* Tool output.
* Internal data transfer.

Gợi ý:

```text
src/models/
├── common.py
├── auth.py
├── vehicle.py
├── parking.py
├── reservation.py
├── guest.py
├── approval.py
├── notification.py
└── agent.py
```

Ví dụ response chung:

```python
from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
```

Lưu ý:

* `src/models/` trong dự án này là Pydantic schemas.
* Không mặc định xem đây là thư mục SQLAlchemy ORM.
* Nếu sử dụng SQLAlchemy, ORM entities có thể được đặt trong `src/services/database.py` ở giai đoạn đầu hoặc bổ sung một module con rõ ràng như `src/services/db_models.py`.
* Không đổi ý nghĩa thư mục `models` mà không cập nhật tài liệu.

---

## 8.4 `src/services/`

Chứa business logic và integration logic.

Đây là lớp nguồn sự thật cho nghiệp vụ.

Gợi ý:

```text
src/services/
├── auth_service.py
├── database.py
├── vehicle_service.py
├── parking_service.py
├── reservation_service.py
├── guest_service.py
├── approval_service.py
├── notification_service.py
├── policy_service.py
├── rag_service.py
├── llm_service.py
├── slot_provider.py
├── audit_service.py
└── security_service.py
```

### Service được phép

* Truy cập repository/database layer.
* Thực hiện business rule.
* Quản lý transaction.
* Gọi Supabase.
* Gọi embedding/LLM ở service phù hợp.
* Ghi audit log.
* Gọi SlotProvider.

### Service không được

* Phụ thuộc vào giao diện Next.js.
* Trả response FastAPI trực tiếp.
* Phụ thuộc vào Agent state.
* Tin tưởng role do LLM cung cấp.
* Đưa toàn bộ dữ liệu nhạy cảm cho LLM.

### Business rules

Do cấu trúc mới không có thư mục `rules/`, business rule được đặt trong service tương ứng hoặc file:

```text
src/services/rule_engine.py
```

Quy tắc:

* Rule dùng ở nhiều service phải nằm trong `rule_engine.py`.
* Rule chỉ dùng riêng một nghiệp vụ có thể nằm trong service đó.
* Không lặp lại rule trong Agent tool.

### Database và repository

Do cấu trúc mới không có thư mục `repositories/`, giai đoạn MVP sử dụng một trong hai cách:

#### Cách ưu tiên cho MVP

```text
src/services/database.py
src/services/<domain>_service.py
```

Trong đó:

* `database.py`: session, engine, base, transaction helpers.
* Các service: truy vấn nghiệp vụ tương ứng.

#### Khi code database lớn hơn

Được phép bổ sung:

```text
src/services/repositories/
```

nhưng không tạo thêm kiến trúc phức tạp nếu chưa cần.

---

## 8.5 `src/config.py`

Chứa Pydantic Settings và cấu hình môi trường.

Ví dụ:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ParkSmart AI"
    app_env: str = "development"
    debug: bool = False

    database_url: str

    supabase_url: str
    supabase_jwt_secret: str
    supabase_service_role_key: str | None = None

    openai_api_key: str
    openai_model: str = "gpt-4o-mini"

    enable_slot_simulator: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Quy tắc:

* Không hard-code secret.
* Không commit `.env`.
* Không đọc environment variables rải rác trong nhiều file.
* Các module phải sử dụng `get_settings()`.

---

## 8.6 `src/main.py`

Là entry point của FastAPI.

Trách nhiệm:

* Khởi tạo FastAPI.
* Đăng ký router.
* Cấu hình CORS.
* Cấu hình exception handler.
* Khởi tạo lifecycle cần thiết.
* Cung cấp health endpoint.

Ví dụ:

```python
from fastapi import FastAPI

from src.api.routes import api_router
from src.config import get_settings


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

Không đặt business logic trong `main.py`.

---

## 8.7 `tests/`

Chứa toàn bộ test tự động bằng pytest.

```text
tests/
├── test_agents/
└── test_api/
```

Được phép bổ sung:

```text
tests/
├── test_agents/
├── test_api/
├── test_services/
├── conftest.py
└── fixtures/
```

### `tests/test_agents/`

Kiểm thử:

* Intent routing.
* Graph transition.
* Tool selection.
* Tool input validation.
* Tool error handling.
* Không bịa dữ liệu.
* HITL routing.
* Policy retrieval.
* Agent response.

### `tests/test_api/`

Kiểm thử:

* Health endpoint.
* Authentication.
* Authorization.
* Request validation.
* Response schema.
* Vehicle endpoints.
* Reservation endpoints.
* Guest endpoints.
* Approval endpoints.
* Agent endpoint.

### `tests/test_services/`

Nếu được bổ sung, kiểm thử:

* Rule engine.
* Database transaction.
* Vehicle limit.
* Reservation concurrency.
* Approval transition.
* Guest validity.

---

## 8.8 `scripts/`

Chứa AI logging hooks và utility script.

```text
scripts/
├── log_hook.py
├── log_antigravity.py
├── log_manual.py
├── submit_log.py
└── setup_hooks.sh
```

### Mục đích

* Ghi nhận việc sử dụng AI trong quá trình phát triển.
* Hỗ trợ nhiều công cụ AI.
* Chuẩn bị dữ liệu minh chứng hoặc reflection.
* Submit log theo quy trình của nhóm.

### Quy tắc bảo mật

AI logging không được lưu:

* API key.
* Access token.
* Supabase service role key.
* Database URL có mật khẩu.
* Dữ liệu thật của cư dân.
* Biển số thật chưa được che.
* Nội dung audit log nhạy cảm.
* File `.env`.

Các log phải được lọc trước khi ghi.

---

## 8.9 `.claude/`, `.codex/`, `.cursor/`, `.gemini/`

Chứa cấu hình hoặc rule riêng cho từng AI coding tool.

Các cấu hình phải:

* Dẫn AI đến `AI_PROJECT_CONTEXT.md`.
* Nhắc AI không tự thay đổi kiến trúc.
* Nhắc AI ghi rõ file cần sửa.
* Nhắc AI tạo test.
* Nhắc AI không ghi secret.
* Nhắc AI tuân theo API contract.
* Nhắc AI không đưa dữ liệu nhạy cảm vào prompt hoặc log.

Các thư mục này không chứa business logic của ứng dụng.

---

## 8.10 `.agents/`

Chứa rule và workflow dành cho Antigravity hoặc các Agent coding environment.

Có thể chứa:

```text
.agents/
├── rules.md
├── backend_workflow.md
├── frontend_contract.md
├── agent_workflow.md
└── review_checklist.md
```

Mọi workflow trong `.agents/` phải phù hợp với file context này.

---

## 8.11 `.ai-log/`

Chứa log sử dụng AI được sinh tự động.

Quy tắc:

* Không chỉnh sửa thủ công trừ khi quy trình yêu cầu.
* Không lưu secret.
* Không lưu dữ liệu người dùng thật.
* Không sử dụng log này làm nguồn sự thật của nghiệp vụ.
* Cần quyết định rõ file nào được commit và file nào nằm trong `.gitignore`.

---

## 8.12 `docs/`

Cấu trúc:

```text
docs/
├── guide/
└── architecture_diagram.md
```

### `docs/guide/`

Technical Guidebook gồm 10 chương.

Cấu trúc khuyến nghị:

```text
docs/guide/
├── 01_project_scope.md
├── 02_system_architecture.md
├── 03_database_design.md
├── 04_api_contract.md
├── 05_business_rules.md
├── 06_agent_design.md
├── 07_rag_design.md
├── 08_security.md
├── 09_testing_and_evaluation.md
└── 10_deployment_and_demo.md
```

Ngoài ra phải có:

```text
docs/AI_PROJECT_CONTEXT.md
```

File này được đặt trực tiếp trong `docs/`, không nằm trong `docs/guide/`, để các AI tool dễ tìm.

### `docs/architecture_diagram.md`

Chứa sơ đồ kiến trúc bằng Mermaid hoặc ASCII.

Sơ đồ phải thể hiện:

```text
Next.js
    ↓
Supabase Auth
    ↓
FastAPI
    ↓
Services
    ├── PostgreSQL
    ├── SlotProvider
    ├── LangGraph
    └── pgvector
```

---

## 8.13 `eval/`

Chứa dữ liệu và kết quả đánh giá Agent.

Gợi ý:

```text
eval/
├── datasets/
│   ├── intent_cases.json
│   ├── tool_cases.json
│   ├── rag_cases.json
│   └── safety_cases.json
├── results/
└── run_eval.py
```

Không đặt pytest thông thường trong `eval/`.

Phân biệt:

* `tests/`: kiểm tra code và hành vi có tính xác định.
* `eval/`: đo chất lượng Agent, LLM, retrieval và response.

---

## 8.14 `presentation/`

Chứa tài liệu Demo Day:

```text
presentation/
├── slides/
├── assets/
├── demo_script.md
└── backup_video.md
```

Không đặt source code ứng dụng trong đây.

---

## 8.15 `.github/workflows/`

Chứa GitHub Actions.

CI tối thiểu:

* Cài dependencies.
* Chạy lint.
* Chạy type check nếu có.
* Chạy pytest.
* Kiểm tra Docker build.
* Kiểm tra secret không bị commit.

CD chỉ được thêm sau khi môi trường deploy đã ổn định.

---

## 8.16 `.github/hooks/`

Chứa Copilot hook config hoặc cấu hình hook liên quan GitHub.

Không nhầm với Git hooks cục bộ.

Hook phải tuân thủ quy tắc AI logging và bảo mật.

---

## 8.17 `Dockerfile`

Sử dụng multi-stage build nếu phù hợp.

Yêu cầu:

* Image nhỏ gọn.
* Không copy `.env`.
* Không chứa secret.
* Chạy ứng dụng bằng user không phải root nếu dễ triển khai.
* Có command khởi động FastAPI.
* Tương thích Railway hoặc nền tảng Docker.

Lệnh chạy dự kiến:

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

---

## 8.18 `docker-compose.yml`

Điều phối các service local.

Tối thiểu:

```text
backend
database
```

Có thể bổ sung:

```text
frontend
```

nếu frontend được đưa vào cùng repository.

Các service dự kiến:

```yaml
services:
  database:
    image: pgvector/pgvector:pg16

  backend:
    build: .
    depends_on:
      - database
```

Docker Compose phải hỗ trợ:

```bash
docker compose up --build
```

---

## 8.19 `README_boilerplate.md`

Là template README dành cho nhóm.

Khi bắt đầu dự án, Leader nên tạo:

```text
README.md
```

từ `README_boilerplate.md`.

README chính phải có:

* Mô tả dự án.
* Thành viên.
* Tech stack.
* Cấu trúc thư mục.
* Cách cấu hình `.env`.
* Cách chạy Docker.
* Cách chạy backend.
* Cách chạy test.
* Cách chạy Agent eval.
* Cách cài AI logging hooks.
* Quy trình Git.
* Link demo khi deploy.

---

# 9. Kiến trúc tổng thể

```text
┌───────────────────────────────────────────┐
│                Next.js                    │
│                                           │
│ Login                                     │
│ Resident Dashboard                        │
│ Security Dashboard                        │
│ Admin Dashboard                           │
│ Parking Map                               │
│ Agent Chat                                │
│ Notifications                             │
└───────────────────┬───────────────────────┘
                    │
                    │ HTTPS REST
                    │ Supabase Realtime
                    ▼
┌───────────────────────────────────────────┐
│               FastAPI                     │
│                                           │
│ src/main.py                               │
│ src/api/routes.py                         │
│ Pydantic models                           │
│ Authentication and authorization          │
└───────────────────┬───────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────┐
│             Service Layer                 │
│                                           │
│ Vehicle service                           │
│ Parking service                           │
│ Reservation service                       │
│ Guest service                             │
│ Approval service                          │
│ Rule engine                               │
│ Slot provider                             │
│ Audit service                             │
│ RAG service                               │
└───────┬─────────────────┬─────────────────┘
        │                 │
        ▼                 ▼
┌───────────────┐   ┌──────────────────────┐
│ PostgreSQL    │   │ LangGraph Agent      │
│ + pgvector    │   │                      │
│               │   │ State                │
│ Business data │   │ Nodes                │
│ Knowledge     │   │ Tools                │
└───────────────┘   └──────────────────────┘
```

---

# 10. Quy tắc kiến trúc bắt buộc

## 10.1 Luồng API

```text
Request
  ↓
FastAPI Route
  ↓
Pydantic Validation
  ↓
Authentication/Authorization
  ↓
Service
  ↓
Business Rule
  ↓
Database
  ↓
Pydantic Response
```

## 10.2 Luồng Agent

```text
User message
  ↓
Agent API
  ↓
LangGraph
  ↓
Intent routing
  ↓
Agent Tool
  ↓
Service
  ↓
Business Rule
  ↓
Database hoặc RAG
  ↓
Structured tool result
  ↓
Agent response
```

## 10.3 Điều cấm

* LLM không được truy cập database trực tiếp.
* LLM không được sinh SQL để chạy.
* Tool không được tự viết lại business rule.
* Route không được chứa business logic phức tạp.
* Agent không được tự quyết định authorization.
* Agent không được tự duyệt approval.
* Agent không được tự tạo số lượng slot trống.
* RAG không được dùng để lấy trạng thái realtime.
* Frontend không được chứa service role key.
* Không sử dụng dữ liệu thật trong demo.
* Không lưu secret trong AI log.

---

# 11. Database tối thiểu

Mặc dù cấu trúc repository không có thư mục database riêng, database vẫn là thành phần bắt buộc của hệ thống.

Các bảng tối thiểu:

```text
profiles
households
household_members
vehicles
parking_cards
parking_areas
parking_slots
reservations
guest_registrations
approval_requests
notifications
parking_policies
knowledge_chunks
agent_messages
audit_logs
```

## 11.1 Enum và trạng thái thống nhất

### User role

```text
resident
security
admin
```

### Vehicle status

```text
pending
active
rejected
blocked
inactive
```

### Slot status

```text
available
reserved
occupied
maintenance
```

### Reservation status

```text
active
used
cancelled
expired
```

### Approval status

```text
pending
approved
rejected
cancelled
```

### Guest status

```text
registered
checked_in
checked_out
expired
cancelled
```

Không tự ý sử dụng trạng thái khác như:

```text
accepted
confirmed
done
waiting
```

cho cùng một ý nghĩa.

---

# 12. Business rules chính

## 12.1 Đăng ký phương tiện

### BR-VEH-001

Biển số phải được chuẩn hóa trước khi kiểm tra trùng.

Ví dụ:

```text
30A-123.45
30A 12345
30a12345
```

phải được chuẩn hóa về cùng một định dạng kiểm tra.

### BR-VEH-002

Một biển số đang gắn với xe `active` hoặc `pending` không được đăng ký lại.

### BR-VEH-003

Nếu số xe đang hoạt động nhỏ hơn `vehicle_limit`:

* Tạo xe.
* Đặt trạng thái `active`.
* Có thể tạo thẻ xe tùy phạm vi triển khai.

### BR-VEH-004

Nếu số xe đang hoạt động bằng hoặc vượt `vehicle_limit`:

* Tạo xe với trạng thái `pending`.
* Tạo approval request.
* Không kích hoạt xe.
* Không cho xe đặt chỗ.

---

## 12.2 Reservation

### BR-RES-001

Chỉ xe `active` được đặt chỗ.

### BR-RES-002

Slot phải có trạng thái `available`.

### BR-RES-003

Một xe chỉ có tối đa một reservation `active`.

### BR-RES-004

Một slot chỉ có tối đa một reservation `active`.

### BR-RES-005

Tạo reservation và đổi slot sang `reserved` phải nằm trong cùng transaction.

### BR-RES-006

Khi reservation bị hủy hoặc hết hạn:

* Reservation được cập nhật trạng thái.
* Slot trở lại `available`, trừ khi slot đã chuyển sang `occupied` hoặc `maintenance`.

---

## 12.3 Xe khách

### BR-GUEST-001

`valid_until` phải lớn hơn `valid_from`.

### BR-GUEST-002

Bảo vệ chỉ check-in xe đang trong thời gian hợp lệ.

### BR-GUEST-003

Xe đã check-out không được check-in lại trong cùng đăng ký.

### BR-GUEST-004

Một biển số được đăng ký bởi nhiều căn hộ trong cùng khoảng thời gian phải được cảnh báo.

---

## 12.4 Approval

### BR-APP-001

Chỉ `admin` được approve hoặc reject.

### BR-APP-002

Không được xử lý lại yêu cầu không còn ở trạng thái `pending`.

### BR-APP-003

Approve/reject phải tạo audit log.

### BR-APP-004

Approve/reject phải tạo notification cho requester.

---

## 12.5 Agent

### BR-AI-001

Agent không được tự tạo dữ liệu slot.

### BR-AI-002

Agent chỉ nói thao tác thành công khi tool trả:

```json
{
  "success": true
}
```

### BR-AI-003

Agent không được tự approve yêu cầu.

### BR-AI-004

Agent không dùng RAG để trả lời trạng thái realtime.

### BR-AI-005

Nếu tool lỗi, Agent phải thông báo không thể hoàn thành thao tác và không được giả định kết quả.

---

# 13. LangGraph Agent

## 13.1 Graph tổng quát

```text
START
  ↓
load_user_context
  ↓
classify_intent
  ├── CHECK_SLOT
  │      ↓
  │   get_available_slots
  │
  ├── RESERVE_SLOT
  │      ↓
  │   validate_reservation
  │      ↓
  │   reserve_slot
  │
  ├── CANCEL_RESERVATION
  │      ↓
  │   cancel_reservation
  │
  ├── REGISTER_VEHICLE
  │      ↓
  │   register_vehicle
  │      ├── active
  │      └── approval_required
  │
  ├── REGISTER_GUEST
  │      ↓
  │   register_guest_vehicle
  │
  ├── CHECK_REQUEST_STATUS
  │      ↓
  │   get_request_status
  │
  ├── POLICY_QUESTION
  │      ↓
  │   retrieve_policy
  │
  └── UNKNOWN
         ↓
      request_clarification
  ↓
generate_response
  ↓
END
```

Agent là workflow có kiểm soát, không phải Agent tự trị toàn quyền.

---

# 14. Agent tools

Các tool tối thiểu:

```text
get_my_vehicles
register_vehicle
get_available_slots
reserve_slot
cancel_reservation
get_parking_guidance
register_guest_vehicle
get_request_status
search_parking_policy
```

## 14.1 Tool result format

Thành công:

```json
{
  "success": true,
  "code": "RESERVATION_CREATED",
  "message": "Đặt chỗ thành công.",
  "data": {
    "reservation_id": "uuid",
    "slot_code": "B1-A-03"
  }
}
```

Thất bại:

```json
{
  "success": false,
  "code": "SLOT_NOT_AVAILABLE",
  "message": "Vị trí này hiện không còn trống.",
  "data": null
}
```

Tool không được ném raw database exception cho LLM.

---

# 15. RAG

## 15.1 Đưa vào RAG

* Nội quy gửi xe.
* Quy trình cấp thẻ.
* Chính sách định mức.
* Quy định xe khách.
* Quy trình mất thẻ.
* Thời gian hoạt động.
* FAQ.

## 15.2 Không đưa vào RAG

* Trạng thái slot.
* Reservation.
* Danh sách xe.
* Thông tin căn hộ.
* Lịch sử ra vào.
* Approval request.
* Notification.
* Audit log.
* Role và permission.

## 15.3 Quy tắc retrieval

* Chỉ trả lời dựa trên chunk phù hợp.
* Nếu không có context phù hợp, nói chưa đủ thông tin.
* Không tự tạo chính sách.
* Không lưu dữ liệu cá nhân vào embedding.
* Metadata nên có nguồn tài liệu và mục nội quy.

---

# 16. API contract cơ bản

## User

```http
GET /api/v1/me
```

## Vehicle

```http
GET    /api/v1/vehicles
POST   /api/v1/vehicles
PATCH  /api/v1/vehicles/{vehicle_id}
POST   /api/v1/vehicles/{vehicle_id}/deactivate
```

## Parking

```http
GET /api/v1/parking/areas
GET /api/v1/parking/areas/{area_id}/availability
GET /api/v1/parking/slots
```

## Reservation

```http
POST   /api/v1/reservations
GET    /api/v1/reservations/me
DELETE /api/v1/reservations/{reservation_id}
GET    /api/v1/reservations/{reservation_id}/guidance
```

## Guest

```http
POST /api/v1/guest-registrations
GET  /api/v1/guest-registrations/me
```

## Security

```http
GET  /api/v1/security/guest-registrations/today
POST /api/v1/security/guest-registrations/{guest_id}/check-in
POST /api/v1/security/guest-registrations/{guest_id}/check-out
```

## Approval

```http
GET  /api/v1/admin/approval-requests
GET  /api/v1/admin/approval-requests/{request_id}
POST /api/v1/admin/approval-requests/{request_id}/approve
POST /api/v1/admin/approval-requests/{request_id}/reject
```

## Agent

```http
POST /api/v1/agent/chat
GET  /api/v1/agent/conversations/{conversation_id}
```

## Simulator

```http
POST /api/v1/simulator/slots/{slot_id}/status
POST /api/v1/simulator/scenarios/rush-hour
POST /api/v1/simulator/scenarios/reset
```

Simulator chỉ được bật trong development hoặc demo.

---

# 17. API response format

## Thành công

```json
{
  "success": true,
  "data": {},
  "message": "Operation completed."
}
```

## Thất bại

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Thông báo có thể hiển thị cho người dùng.",
    "details": null
  }
}
```

## HTTP status

```text
200: Thành công
201: Tạo mới thành công
400: Yêu cầu nghiệp vụ không hợp lệ
401: Chưa xác thực
403: Không có quyền
404: Không tìm thấy resource
409: Xung đột dữ liệu hoặc trạng thái
422: Pydantic validation error
500: Lỗi hệ thống
```

---

# 18. Error code tối thiểu

## Authentication

```text
AUTH_REQUIRED
INVALID_TOKEN
ROLE_FORBIDDEN
RESOURCE_FORBIDDEN
```

## Vehicle

```text
VEHICLE_NOT_FOUND
DUPLICATE_PLATE_NUMBER
VEHICLE_LIMIT_EXCEEDED
VEHICLE_NOT_ACTIVE
```

## Parking

```text
PARKING_AREA_NOT_FOUND
SLOT_NOT_FOUND
SLOT_NOT_AVAILABLE
```

## Reservation

```text
RESERVATION_NOT_FOUND
ACTIVE_RESERVATION_EXISTS
RESERVATION_ALREADY_COMPLETED
```

## Guest

```text
GUEST_REGISTRATION_NOT_FOUND
GUEST_REGISTRATION_EXPIRED
GUEST_ALREADY_CHECKED_IN
GUEST_ALREADY_CHECKED_OUT
```

## Approval

```text
APPROVAL_REQUEST_NOT_FOUND
APPROVAL_ALREADY_PROCESSED
APPROVAL_REQUIRED
```

## Agent

```text
UNKNOWN_INTENT
TOOL_EXECUTION_FAILED
RAG_CONTEXT_NOT_FOUND
AGENT_INTERNAL_ERROR
```

---

# 19. Bảo mật

## Quy tắc bắt buộc

* Không commit `.env`.
* Không đặt Supabase service role key ở frontend.
* Không log access token.
* Không log OpenAI API key.
* Không nhận `user_id` từ LLM làm nguồn tin cậy.
* Backend lấy user từ JWT.
* Kiểm tra ownership ở backend.
* Không gửi toàn bộ lịch sử ra vào cho LLM.
* Không gửi audit log cho LLM.
* Không đưa dữ liệu người dùng vào vector database.
* Dữ liệu demo không sử dụng thông tin thật.
* Simulator chỉ bật ở môi trường demo/development.
* Approval phải có audit log.
* Biển số trong log phải được che.

Ví dụ:

```text
30A-***.45
```

## AI logging

Các script logging phải tự động loại bỏ:

```text
OPENAI_API_KEY
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_JWT_SECRET
DATABASE_URL
Authorization header
Cookie
Access token
Refresh token
```

---

# 20. Kiểm thử

## 20.1 Agent tests

Tối thiểu:

* Phân loại đúng intent.
* Chọn đúng tool.
* Truyền đúng tham số.
* Không gọi tool ngoài quyền.
* Không bịa slot.
* Không báo thành công khi tool thất bại.
* Không tự approve.
* Không trả dữ liệu người khác.
* Không trả chính sách nếu retrieval không có nguồn.

## 20.2 API tests

Tối thiểu:

* Health endpoint.
* Token không hợp lệ.
* Resident không gọi được API admin.
* Security không sửa approval.
* Đăng ký biển số trùng.
* Vượt định mức tạo approval.
* Xe inactive không đặt chỗ.
* Slot không available thì không đặt được.
* Hai request cùng đặt một slot thì chỉ một request thành công.
* Approval không được xử lý hai lần.
* Xe khách hết hạn không được check-in.

## 20.3 Agent evaluation

Tối thiểu 30 case.

Khuyến nghị:

```text
8 intent routing cases
8 tool selection cases
5 RAG cases
5 safety cases
4 tool error cases
```

---

# 21. Phân công theo cấu trúc mới

## Leader

Chịu trách nhiệm chính:

```text
src/main.py
src/config.py
docs/
.github/workflows/
Dockerfile
docker-compose.yml
README.md
```

Nhiệm vụ:

* Khóa kiến trúc.
* Khóa API contract.
* Khóa database schema.
* Khóa business rules.
* Tạo repository skeleton.
* Cấu hình CI.
* Review PR.
* Tích hợp các module.
* Deploy backend.
* Quản lý issue.
* Chuẩn bị Demo Day.

Khi Leader hỏi AI, AI phải ưu tiên:

* Tính nhất quán.
* Khả năng tích hợp.
* Phát hiện contract conflict.
* Giải pháp vừa đủ cho MVP.
* Test và deployment.
* Không mở rộng phạm vi.

---

## Đoàn

Chịu trách nhiệm chính:

```text
src/services/database.py
src/services/auth_service.py
src/services/vehicle_service.py
src/services/parking_service.py
src/services/reservation_service.py
src/services/guest_service.py
src/services/approval_service.py
src/services/notification_service.py
src/services/rule_engine.py
src/services/audit_service.py
src/models/
tests/test_api/
tests/test_services/
```

Nhiệm vụ:

* Database connection.
* ORM entities và migration.
* Authentication.
* Authorization.
* Business services.
* Rule engine.
* Transaction.
* API schemas.
* Backend tests.

Khi Đoàn hỏi AI, AI phải:

* Tách API schema và business service.
* Không đặt logic dài trong route.
* Dùng transaction cho reservation.
* Viết test cho business rule.
* Không thay đổi Agent graph nếu không liên quan.
* Cảnh báo khi thay đổi database hoặc API contract.

---

## Quang Thành

Frontend có thể nằm trong repository riêng hoặc được thêm vào repository sau.

Chịu trách nhiệm:

* Next.js App Router.
* Supabase Auth.
* Protected routes.
* Resident UI.
* Parking map.
* Reservation UI.
* Guest UI.
* Security UI.
* Admin approval UI.
* Agent chat UI.
* Notification UI.
* Realtime.

Frontend phải gọi API đã được định nghĩa trong context này.

Khi Quang Thành hỏi AI, AI phải:

* Dùng TypeScript.
* Không tự đổi API response.
* Có loading, error và empty state.
* Không lưu secret.
* Không thực hiện authorization chỉ bằng frontend.
* Không gọi trực tiếp database cho nghiệp vụ.
* Giữ giao diện đơn giản, dễ demo.

---

## Phú Thành

Chịu trách nhiệm chính:

```text
src/agents/
src/services/llm_service.py
src/services/rag_service.py
src/services/policy_service.py
eval/
tests/test_agents/
```

Nhiệm vụ:

* Agent state.
* LangGraph graph.
* Nodes.
* Tools.
* Intent routing.
* RAG ingestion.
* Retrieval.
* Structured output.
* Prompt.
* Guardrails.
* Agent tests.
* Agent evaluation.

Khi Phú Thành hỏi AI, AI phải:

* Không tạo Agent quá tự trị.
* Không truy cập database trực tiếp.
* Tool phải gọi service.
* Không lặp business rule.
* Không dùng RAG cho realtime data.
* Không để Agent bịa kết quả.
* Viết test cho graph và tool.
* Giữ context nhỏ và tránh dữ liệu nhạy cảm.

---

# 22. Quy trình Git

## Branch chính

```text
main
develop
```

## Feature branch

```text
feat/<issue-number>-<feature-name>
fix/<issue-number>-<bug-name>
docs/<issue-number>-<document-name>
test/<issue-number>-<test-name>
```

Ví dụ:

```text
feat/12-vehicle-service
feat/18-agent-tools
feat/21-parking-map
fix/31-reservation-conflict
```

## Quy tắc

* Không push trực tiếp vào `main`.
* Mỗi issue tương ứng một branch.
* Database change phải có migration.
* API change phải cập nhật API contract.
* Agent tool change phải cập nhật Agent contract hoặc test.
* PR phải ghi cách kiểm tra.
* PR giao diện phải có screenshot.
* Mỗi PR cần ít nhất một người review.
* Merge thường xuyên vào `develop`.
* Không chờ đến cuối tuần mới tích hợp.

## Commit convention

```text
feat: add vehicle registration service
fix: prevent duplicate slot reservation
test: add agent routing cases
docs: update API contract
refactor: separate policy retrieval service
chore: configure CI workflow
```

---

# 23. Kế hoạch hai tuần

## Ngày 1

* Chốt context.
* Chốt architecture.
* Chốt database.
* Chốt API contract.
* Chốt business rules.
* Tạo repository structure.
* Tạo issue.
* Cấu hình branch.

## Ngày 2–4

* FastAPI skeleton.
* Config.
* Database connection.
* Authentication.
* Authorization.
* Pydantic schemas.
* Agent graph skeleton.
* Mock tools.
* Test health và auth.
* Docker local.

## Ngày 4–7

* Vehicle service.
* Parking service.
* Reservation.
* Guest registration.
* Slot simulator.
* Frontend login.
* Frontend parking map.
* Agent tool adapters.

## Ngày 6–10

* LangGraph hoàn chỉnh.
* RAG.
* Approval workflow.
* Notification.
* Admin approval UI.
* Security UI.
* Agent chat.
* Realtime.

## Ngày 10–12

* Unit tests.
* API integration tests.
* Agent evaluation.
* Security tests.
* Fix bug.
* Hoàn thiện UI.
* Kiểm tra AI logs.

## Ngày 13–14

* Docker production.
* Deploy.
* Seed demo data.
* Smoke test.
* Demo script.
* Slides.
* Video dự phòng.
* Release `v0.1.0-mvp`.

---

# 24. Definition of Done

Một chức năng chỉ hoàn thành khi:

* Code chạy được.
* Có Pydantic validation.
* Có xử lý lỗi.
* Có kiểm tra authorization nếu cần.
* Có test phù hợp.
* Không chứa secret.
* Không phá API contract.
* Có migration nếu thay đổi database.
* Có tài liệu nếu thay đổi hành vi.
* Đã được review.
* Đã merge vào `develop`.

MVP hoàn thành khi:

* Ba vai trò đăng nhập được.
* Cư dân quản lý xe được.
* Cư dân xem và đặt slot được.
* Slot cập nhật realtime.
* Cư dân đăng ký xe khách được.
* Bảo vệ xử lý xe khách được.
* Agent gọi đúng tool.
* Agent không bịa slot.
* Đăng ký vượt định mức tạo approval.
* Admin duyệt hoặc từ chối được.
* Cư dân nhận notification.
* Có audit log.
* Có pytest.
* Có Agent evaluation.
* Docker build thành công.
* Backend và frontend được deploy.
* Luồng demo chạy ổn định.

---

# 25. Hướng dẫn bắt buộc cho AI Assistant

Khi hỗ trợ dự án này, AI phải:

1. Đọc toàn bộ context trước khi trả lời.
2. Không tự đổi tech stack.
3. Không tự thay đổi cấu trúc thư mục.
4. Không mở rộng ngoài MVP.
5. Nếu yêu cầu xung đột với context, phải nêu rõ.
6. Chỉ hỏi lại khi thiếu thông tin ảnh hưởng trực tiếp đến contract.
7. Với chi tiết nhỏ, chọn giải pháp đơn giản nhất và ghi rõ giả định.
8. Khi viết code phải nêu:

   * File cần tạo hoặc sửa.
   * Nội dung code.
   * Dependency.
   * Lệnh chạy.
   * Cách test.
9. Không viết pseudo-code nếu được yêu cầu implementation.
10. Không thay đổi API hoặc schema mà không cảnh báo.
11. Không đặt business logic trong Agent tool.
12. Không cho LLM truy cập database.
13. Không cho LLM quyết định quyền.
14. Không cho LLM tự approve.
15. Không gửi dữ liệu nhạy cảm vào prompt.
16. Không ghi secret vào AI logs.
17. Luôn đề xuất hoặc viết test phù hợp.
18. Ưu tiên giải pháp hoàn thành được trong hai tuần.
19. Không đề xuất microservice hoặc Kubernetes.
20. Không tuyên bố thao tác thành công nếu tool chưa xác nhận.
21. Không tạo thêm thư mục cấp cao ngoài cấu trúc đã chốt nếu chưa được Leader chấp thuận.
22. Được phép bổ sung file hoặc thư mục con khi thực sự cần, nhưng phải giải thích lý do.
23. `src/models/` luôn được hiểu là Pydantic schemas.
24. Business logic phải nằm trong `src/services/`.
25. Agent implementation phải nằm trong `src/agents/`.
26. API endpoints phải đi qua `src/api/routes.py` hoặc router được include từ đó.
27. Mọi cấu hình môi trường phải đi qua `src/config.py`.
28. Mọi test tự động phải nằm trong `tests/`.
29. Agent quality evaluation phải nằm trong `eval/`.
30. Các script AI logging không được can thiệp vào runtime của ứng dụng.

---

# 26. Mẫu prompt cho từng thành viên

Sau khi cung cấp file context cho AI, sử dụng mẫu sau:

```text
Bạn đang hỗ trợ dự án ParkSmart AI.

Hãy đọc và tuân thủ toàn bộ AI_PROJECT_CONTEXT.md đã được cung cấp.

Thông tin nhiệm vụ:
- Thành viên thực hiện:
- Vai trò:
- Issue:
- Mục tiêu:
- File liên quan:
- API liên quan:
- Database liên quan:
- Business rule liên quan:
- Kết quả mong muốn:

Yêu cầu khi trả lời:
1. Không thay đổi kiến trúc và cấu trúc thư mục chung.
2. Chỉ giải quyết nhiệm vụ trong phạm vi issue.
3. Nêu rõ file cần tạo hoặc sửa.
4. Cung cấp code hoàn chỉnh, dễ hiểu.
5. Nêu dependency và lệnh chạy.
6. Nêu cách kiểm thử.
7. Cảnh báo nếu nhiệm vụ xung đột với API, database hoặc business rule.
8. Không ghi secret hoặc dữ liệu người dùng thật.
9. Không tạo business logic trùng lặp giữa Agent tool và service.
10. Giữ giải pháp phù hợp với MVP hai tuần.
```

---

# 27. Nguồn sự thật của dự án

Khi có xung đột, ưu tiên theo thứ tự:

1. Quyết định mới nhất của Leader đã được ghi trong issue hoặc tài liệu.
2. `docs/AI_PROJECT_CONTEXT.md`.
3. `docs/guide/04_api_contract.md`.
4. `docs/guide/03_database_design.md`.
5. `docs/guide/05_business_rules.md`.
6. `docs/guide/06_agent_design.md`.
7. Code đã merge vào `develop`.
8. Nội dung trao đổi chưa được ghi lại.
9. Đề xuất riêng của AI Assistant.

Đề xuất do AI tạo ra không tự động trở thành quyết định chính thức của dự án.
