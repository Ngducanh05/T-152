# PARKSMART AI — KẾ HOẠCH TRIỂN KHAI DỰ ÁN TRONG 2 TUẦN

## 1. Thông tin chung

### Tên dự án

**ParkSmart AI – Agent Quản lý và Điều phối Gửi xe Thông minh**

### Mục tiêu

Xây dựng MVP có thể chạy, kiểm thử, deploy và demo được, hỗ trợ:

- Đăng nhập và phân quyền.
- Quản lý phương tiện cư dân.
- Tra cứu và đặt chỗ đỗ.
- Hướng dẫn tầng, khu và slot phù hợp.
- Đăng ký xe khách.
- HITL cho yêu cầu đăng ký xe vượt định mức.
- Agent hỏi đáp nội quy và gọi tool nghiệp vụ.
- Realtime trạng thái slot, approval và notification.

### Thành viên

| Thành viên | Trách nhiệm chính |
|---|---|
| Leader | Kiến trúc, quản lý dự án, tài liệu, API contract, tích hợp, CI/CD, deploy |
| Đoàn | Database, backend nghiệp vụ, authentication, rule engine, backend test |
| Quang Thành | Next.js, Supabase Auth, UI/UX, parking map, realtime |
| Phú Thành | LangGraph Agent, tools, RAG, prompt, eval và Agent test |

---

# 2. Phạm vi MVP

## 2.1 Chức năng bắt buộc

### Authentication

- Supabase Auth.
- Ba role:
  - `resident`
  - `security`
  - `admin`
- FastAPI xác minh access token.
- Backend kiểm tra authorization.

### Vehicle management

- Xem danh sách xe.
- Đăng ký xe.
- Cập nhật thông tin.
- Ngừng sử dụng xe.
- Kiểm tra biển số trùng.
- Xe vượt định mức chuyển sang `pending`.

### Parking management

- Xem khu và tầng.
- Xem số slot trống.
- Xem trạng thái từng slot.
- Đặt chỗ.
- Hủy chỗ.
- Hướng dẫn vị trí.

### Guest registration

- Cư dân đăng ký xe khách.
- Bảo vệ xem xe khách hợp lệ.
- Bảo vệ check-in/check-out.

### HITL

- Xe vượt định mức tạo `approval_request`.
- Admin approve hoặc reject.
- Cập nhật trạng thái vehicle.
- Tạo notification.
- Ghi audit log.

### AI Agent

Các intent tối thiểu:

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

Chỉ dùng cho:

- Nội quy gửi xe.
- Quy trình cấp thẻ.
- Chính sách định mức.
- Quy định xe khách.
- Hướng dẫn mất thẻ.
- FAQ.

Không dùng RAG cho:

- Trạng thái slot.
- Reservation.
- Xe của cư dân.
- Approval.
- Notification.
- Dữ liệu ra vào.

## 2.2 Ngoài phạm vi MVP

- Camera thật.
- Cảm biến vật lý.
- Barrier.
- Thanh toán.
- Mobile app riêng.
- Dẫn đường 3D.
- Computer vision chống gian lận.
- Mô hình dự báo phức tạp.
- Microservice.
- Kubernetes.

---

# 3. Cấu trúc repository

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
│   ├── test_api/
│   └── test_services/
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
│   ├── AI_PROJECT_CONTEXT.md
│   ├── architecture_diagram.md
│   └── guide/
│       ├── 01_project_scope.md
│       ├── 02_system_architecture.md
│       ├── 03_database_design.md
│       ├── 04_api_contract.md
│       ├── 05_business_rules.md
│       ├── 06_agent_design.md
│       ├── 07_rag_design.md
│       ├── 08_security.md
│       ├── 09_testing_and_evaluation.md
│       └── 10_deployment_and_demo.md
├── eval/
├── presentation/
├── alembic/
├── .github/
│   ├── workflows/
│   └── hooks/
├── pyproject.toml
├── alembic.ini
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── README.md
└── README_boilerplate.md
```

---

# 4. Kiến trúc hệ thống

## 4.1 Luồng API

```text
Frontend
→ FastAPI Route
→ Pydantic Validation
→ Authentication
→ Authorization
→ Service
→ Business Rule
→ Database
→ Pydantic Response
```

## 4.2 Luồng Agent

```text
User
→ POST /api/v1/agent/chat
→ FastAPI lấy trusted user context
→ LangGraph
→ Intent routing
→ Agent Tool
→ Business Service
→ Database hoặc RAG
→ Structured result
→ Agent response
```

## 4.3 Nguyên tắc bắt buộc

- LLM không truy cập database trực tiếp.
- LLM không tự sinh SQL để chạy.
- Agent tool phải gọi service.
- Agent không quyết định authorization.
- Agent không tự approve.
- Agent không bịa trạng thái slot.
- RAG không dùng cho dữ liệu realtime.
- Backend là nơi kiểm tra quyền.
- PostgreSQL là nguồn sự thật.

---

# 5. Giai đoạn 0 — Khóa yêu cầu và hợp đồng kỹ thuật

## Thời gian

**Ngày 1**

## Mục tiêu

Tạo một nguồn sự thật thống nhất trước khi viết code.

## Công việc của Leader

### 5.1 Hoàn thành tài liệu

Bắt buộc:

```text
docs/AI_PROJECT_CONTEXT.md
docs/guide/01_project_scope.md
docs/guide/02_system_architecture.md
docs/guide/04_api_contract.md
docs/guide/08_security.md
docs/architecture_diagram.md
```

Tạo placeholder:

```text
docs/guide/07_rag_design.md
docs/guide/09_testing_and_evaluation.md
docs/guide/10_deployment_and_demo.md
```

### 5.2 Giao tài liệu

Đoàn:

```text
docs/guide/03_database_design.md
docs/guide/05_business_rules.md
```

Phú Thành:

```text
docs/guide/06_agent_design.md
```

Quang Thành:

- Review API contract.
- Xác nhận dữ liệu frontend cần.
- Liệt kê route và component chính.

### 5.3 Khóa thuật ngữ

Role:

```text
resident
security
admin
```

Vehicle status:

```text
pending
active
rejected
blocked
inactive
```

Slot status:

```text
available
reserved
occupied
maintenance
```

Reservation status:

```text
active
used
cancelled
expired
```

Approval status:

```text
pending
approved
rejected
cancelled
```

## Đầu ra

- Tài liệu được review.
- Có issue cho từng thành viên.
- Có acceptance criteria.
- Không còn tranh luận về scope, role, status, API chính.

## Điều kiện hoàn thành

- Docs được merge vào `develop`.
- Tất cả thành viên hiểu cùng một kiến trúc.
- Mỗi người biết file và module mình phụ trách.

---

# 6. Giai đoạn 1 — Dựng nền tảng hệ thống

## Thời gian

**Ngày 2–4**

## Mục tiêu

Chạy được FastAPI, PostgreSQL, Auth, LangGraph skeleton, frontend login và CI.

## 6.1 Công việc của Leader

Tạo:

```text
pyproject.toml
.env.example
.gitignore
src/config.py
src/main.py
src/api/routes.py
src/models/common.py
Dockerfile
docker-compose.yml
.github/workflows/ci.yml
README.md
```

Hoàn thành:

- FastAPI app.
- `GET /health`.
- `GET /api/v1/health/database`.
- CORS.
- Docker local.
- CI lint, test và Docker build.
- Branch `develop`.
- Branch protection.
- PR template.

## 6.2 Công việc của Đoàn

Tạo:

```text
src/services/database.py
src/services/db_models.py
src/services/auth_service.py
alembic/
alembic.ini
```

Triển khai:

- PostgreSQL async connection.
- SQLAlchemy session.
- Alembic.
- Extension `vector`.
- Bảng `profiles`.
- Supabase access-token validation.
- `GET /api/v1/me`.
- Role lấy từ `profiles.app_role`.
- Test Auth và `/me`.

## 6.3 Công việc của Phú Thành

Tạo:

```text
src/agents/state.py
src/agents/graph.py
src/agents/nodes/classify_intent.py
src/agents/nodes/generate_response.py
src/models/agent.py
tests/test_agents/test_graph.py
```

Triển khai:

- `ParkingAgentState`.
- Graph có ít nhất hai node.
- Rule-based intent mock.
- Mock response.
- `POST /api/v1/agent/chat`.
- Agent nhận `user_id` và `role` từ backend context.
- Agent không tuyên bố thao tác thành công khi chưa có tool thật.

## 6.4 Công việc của Quang Thành

Trong frontend Next.js:

- Khởi tạo App Router.
- Supabase login/logout.
- Protected dashboard.
- API client.
- Gọi `/api/v1/me`.
- Hiển thị tên và role.
- Form Agent chat đơn giản.
- Loading và error state.

## API phải chạy

```http
GET /health
GET /api/v1/health/database
GET /api/v1/me
POST /api/v1/agent/chat
```

## Điều kiện hoàn thành

```text
docker compose up --build
```

sau đó:

- PostgreSQL chạy.
- FastAPI chạy.
- `/health` trả 200.
- `/docs` mở được.
- `/me` trả đúng user.
- Agent graph chạy.
- Frontend login được.
- CI pass.
- pytest pass.

---

# 7. Giai đoạn 2 — Xây dựng nghiệp vụ cốt lõi

## Thời gian

**Ngày 4–7**

## Mục tiêu

Hoàn thành nghiệp vụ không phụ thuộc Agent trước.

## 7.1 Database cần triển khai

```text
households
household_members
vehicles
parking_cards
parking_areas
parking_slots
reservations
guest_registrations
```

## 7.2 Công việc của Đoàn

Tạo các service:

```text
src/services/vehicle_service.py
src/services/parking_service.py
src/services/reservation_service.py
src/services/guest_service.py
src/services/rule_engine.py
src/services/audit_service.py
src/services/slot_provider.py
```

Triển khai:

### Vehicle

- Xem danh sách xe.
- Đăng ký xe.
- Chuẩn hóa biển số.
- Kiểm tra biển số trùng.
- Ngừng sử dụng xe.

### Parking

- Xem khu.
- Xem slot.
- Lọc theo trạng thái.
- Slot Simulator.
- Rush-hour scenario.
- Reset scenario.

### Reservation

- Chỉ xe active được đặt.
- Slot phải available.
- Một xe chỉ có một active reservation.
- Một slot chỉ có một active reservation.
- Transaction chống race condition.
- Hủy và hết hạn reservation.

### Guest

- Đăng ký xe khách.
- Kiểm tra thời gian hợp lệ.
- Check-in/check-out.
- Cảnh báo đăng ký trùng thời gian.

## 7.3 Công việc của Quang Thành

Tạo giao diện:

```text
/dashboard
/vehicles
/parking
/reservations
/guests
/security
```

Component:

```text
VehicleList
VehicleForm
AreaSelector
ParkingSlotGrid
SlotLegend
ReservationDialog
GuestRegistrationForm
SecurityGuestTable
```

Triển khai:

- Parking map dạng grid.
- Màu và text theo trạng thái.
- Form đăng ký xe.
- Form đặt chỗ.
- Form xe khách.
- Realtime slot update.

## 7.4 Công việc của Phú Thành

Tạo Agent tools:

```text
get_my_vehicles
get_available_slots
reserve_slot
cancel_reservation
register_guest_vehicle
get_parking_guidance
```

Nguyên tắc:

- Tool gọi service.
- Tool không gọi SQL.
- Tool không lặp business rule.
- Tool trả structured output.
- Tool lỗi thì Agent không báo thành công.

## API cần hoàn thành

```http
GET    /api/v1/vehicles
POST   /api/v1/vehicles
PATCH  /api/v1/vehicles/{vehicle_id}
POST   /api/v1/vehicles/{vehicle_id}/deactivate

GET    /api/v1/parking/areas
GET    /api/v1/parking/slots
GET    /api/v1/parking/areas/{area_id}/availability

POST   /api/v1/reservations
GET    /api/v1/reservations/me
DELETE /api/v1/reservations/{reservation_id}
GET    /api/v1/reservations/{reservation_id}/guidance

POST   /api/v1/guest-registrations
GET    /api/v1/guest-registrations/me

GET    /api/v1/security/guest-registrations/today
POST   /api/v1/security/guest-registrations/{id}/check-in
POST   /api/v1/security/guest-registrations/{id}/check-out
```

## Điều kiện hoàn thành

Luồng phải chạy không cần Agent:

```text
Frontend
→ API
→ Service
→ Database
→ Realtime
→ Frontend
```

Demo được:

1. Đăng ký xe.
2. Xem slot.
3. Đặt slot.
4. Hủy slot.
5. Đăng ký xe khách.
6. Bảo vệ check-in/check-out.

---

# 8. Giai đoạn 3 — Agent, RAG và HITL

## Thời gian

**Ngày 6–10**

## Mục tiêu

Kết nối AI Agent với nghiệp vụ thật, thêm RAG và approval workflow.

## 8.1 Database cần bổ sung

```text
approval_requests
notifications
parking_policies
knowledge_chunks
agent_messages
audit_logs
```

## 8.2 Công việc của Đoàn

Tạo:

```text
src/services/approval_service.py
src/services/notification_service.py
src/services/policy_service.py
```

Triển khai:

- Vehicle vượt định mức tạo `approval_request`.
- Admin approve/reject.
- Không xử lý approval hai lần.
- Transaction cập nhật vehicle và approval.
- Notification.
- Audit log.
- API xem trạng thái request.

## 8.3 Công việc của Phú Thành

Hoàn thiện:

```text
src/agents/graph.py
src/agents/nodes/
src/agents/tools/
src/services/llm_service.py
src/services/rag_service.py
eval/
```

Triển khai:

- Structured intent classification.
- Tool routing.
- Tool error handling.
- Policy retrieval.
- Chunking.
- Embedding.
- pgvector search.
- No-context fallback.
- Sensitive-data filtering.
- Conversation state.
- 30–50 eval cases.

Agent phải xử lý:

```text
“Bãi B2 còn chỗ không?”
“Đặt cho xe của tôi một chỗ gần lối ra.”
“Tôi muốn đăng ký thêm xe.”
“Đăng ký xe khách đến 10 giờ tối.”
“Yêu cầu của tôi đã được duyệt chưa?”
“Quy định mất thẻ xe là gì?”
```

## 8.4 Công việc của Quang Thành

Tạo:

```text
/agent
/admin/approvals
/notifications
```

Triển khai:

- Agent chat UI.
- Hiển thị tool status.
- Approval table.
- Approval detail.
- Approve/reject.
- Notification center.
- Realtime approval update.

## API cần hoàn thành

```http
GET  /api/v1/admin/approval-requests
GET  /api/v1/admin/approval-requests/{id}
POST /api/v1/admin/approval-requests/{id}/approve
POST /api/v1/admin/approval-requests/{id}/reject

GET  /api/v1/approval-requests/me
GET  /api/v1/notifications
POST /api/v1/notifications/{id}/read

POST /api/v1/agent/chat
GET  /api/v1/agent/conversations/{conversation_id}
```

## Điều kiện hoàn thành

- Agent gọi đúng tool.
- Agent không bịa slot.
- Tool lỗi không bị đổi thành thành công.
- Xe vượt định mức tạo approval.
- Admin duyệt hoặc từ chối.
- Cư dân nhận notification.
- Agent trả lời nội quy dựa trên RAG.
- Không có context thì Agent nói chưa đủ thông tin.

---

# 9. Giai đoạn 4 — Kiểm thử, bảo mật và hoàn thiện

## Thời gian

**Ngày 10–12**

## Mục tiêu

Ổn định hệ thống trước deploy.

## 9.1 Backend tests

- Auth.
- Authorization.
- Ownership.
- Duplicate plate.
- Vehicle limit.
- Reservation transaction.
- Race condition.
- Guest validity.
- Approval transition.
- Notification.
- Audit log.

## 9.2 Frontend tests

- Protected route.
- Role-based navigation.
- Form validation.
- Loading.
- Error.
- Empty state.
- Realtime update.
- Responsive UI.

## 9.3 Agent tests

- Intent đúng.
- Tool đúng.
- Parameter đúng.
- Không gọi tool khi không cần.
- Không bịa slot.
- Không tự approve.
- Không lộ dữ liệu người khác.
- Không trả policy khi RAG không có nguồn.
- Tool lỗi không báo thành công.

## 9.4 Security checks

- Không có `.env` trong Git.
- Không có service role key trong frontend.
- Không log token.
- Không log biển số đầy đủ.
- Không gửi audit log cho LLM.
- Không lưu dữ liệu người dùng trong vector DB.
- AI logs được lọc.
- Simulator chỉ bật ở demo/development.

## 9.5 Agent eval

Tối thiểu:

```text
8 intent cases
8 tool cases
5 RAG cases
5 safety cases
4 error-handling cases
```

Mục tiêu:

| Chỉ số | Mục tiêu |
|---|---:|
| Intent accuracy | ≥ 85% |
| Tool selection accuracy | ≥ 90% |
| Hallucinated slot data | 0 |
| Unauthorized approval | 0 |
| False success after tool error | 0 |

## Điều kiện hoàn thành

- Test pass.
- Không còn bug blocker.
- Demo flow chạy liên tục.
- Có danh sách limitation rõ ràng.
- UI có loading/error/empty state.

---

# 10. Giai đoạn 5 — Deploy và Demo Day

## Thời gian

**Ngày 13–14**

## Mục tiêu

Đưa hệ thống lên môi trường demo ổn định.

## 10.1 Công việc của Leader

- Deploy backend lên Railway.
- Deploy frontend lên Vercel.
- Cấu hình Supabase production.
- Cấu hình CORS.
- Cấu hình environment variables.
- Chạy migration.
- Seed demo data.
- Smoke test.
- Gắn release tag.

## 10.2 Dữ liệu demo

Tài khoản:

```text
resident.demo@parksmart.local
security.demo@parksmart.local
admin.demo@parksmart.local
```

Kịch bản:

- Căn hộ có `vehicle_limit = 1`.
- Resident đã có một xe active.
- Đăng ký xe thứ hai tạo approval.
- B1 còn slot.
- B2 gần đầy.
- Có xe khách đang chờ check-in.

## 10.3 Demo script

1. Resident đăng nhập.
2. Agent kiểm tra slot.
3. Agent đặt slot.
4. Parking map cập nhật.
5. Resident đăng ký thêm xe vượt định mức.
6. Approval được tạo.
7. Admin đăng nhập và approve.
8. Resident nhận notification.
9. Resident đăng ký xe khách.
10. Security check-in xe khách.
11. Agent trả lời nội quy bằng RAG.

## 10.4 Chuẩn bị dự phòng

- Video demo.
- Screenshot.
- Seed script.
- Reset script.
- Danh sách tài khoản demo.
- Slide kiến trúc.
- Slide business value.
- Slide limitation và roadmap.

## Điều kiện hoàn thành

- Frontend mở được.
- Backend health check pass.
- Database migration đúng.
- Demo flow chạy ổn định.
- Có video dự phòng.
- Release `v0.1.0-mvp`.

---

# 11. Quy trình Git

## Branch

```text
main
develop
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

- Không push trực tiếp vào `main`.
- Mỗi issue có một branch.
- Database change phải có migration.
- API change phải cập nhật API contract.
- Agent tool change phải có test.
- PR phải ghi cách test.
- PR frontend phải có screenshot.
- Mỗi PR cần ít nhất một review.
- Merge vào `develop` hằng ngày.
- Không chờ cuối tuần mới tích hợp.

## Commit convention

```text
feat: add vehicle registration service
fix: prevent duplicate slot reservation
test: add agent routing cases
docs: update API contract
refactor: separate policy service
chore: configure CI workflow
```

---

# 12. Milestone theo ngày

## Ngày 1

- Chốt docs.
- Chốt scope.
- Chốt architecture.
- Chốt database.
- Chốt API.
- Chốt Agent design.
- Tạo issue.

## Ngày 2

- FastAPI skeleton.
- Docker.
- PostgreSQL.
- `profiles`.
- Supabase Auth.
- Agent state.

## Ngày 3

- `/me`.
- Agent graph mock.
- Frontend login.
- CI.
- API test.

## Ngày 4

- Tích hợp Giai đoạn 1.
- Tag `milestone-1-foundation`.

## Ngày 5–7

- Vehicle.
- Parking.
- Reservation.
- Guest.
- Parking map.
- Agent tools.

## Ngày 8–10

- HITL.
- Approval.
- Notification.
- RAG.
- Agent thật.
- Admin UI.

## Ngày 11–12

- Test.
- Eval.
- Security review.
- Fix bug.

## Ngày 13

- Deploy.
- Migration.
- Seed.
- Smoke test.

## Ngày 14

- Demo rehearsal.
- Slide.
- Video dự phòng.
- Release.

---

# 13. Definition of Done

Một task chỉ hoàn thành khi:

- Code chạy được.
- Có validation.
- Có xử lý lỗi.
- Có authorization nếu cần.
- Có test.
- Không chứa secret.
- Không phá API contract.
- Có migration nếu đổi database.
- Có cập nhật docs nếu đổi hành vi.
- Được review.
- Merge vào `develop`.

MVP hoàn thành khi:

- Ba role đăng nhập được.
- Vehicle management chạy.
- Parking map chạy.
- Reservation chạy.
- Guest registration chạy.
- Agent gọi đúng tool.
- Agent không bịa dữ liệu.
- HITL chạy.
- Notification chạy.
- Audit log tồn tại.
- Test và eval đạt mục tiêu.
- Backend và frontend deploy.
- Demo flow ổn định.

---

# 14. Việc Leader cần làm đầu tiên

Theo đúng thứ tự:

1. Merge `docs/AI_PROJECT_CONTEXT.md`.
2. Hoàn thành scope, architecture, API contract và security docs.
3. Giao Đoàn hoàn thành database và business rules.
4. Giao Phú Thành hoàn thành Agent design.
5. Yêu cầu Quang Thành review frontend integration.
6. Tạo `develop`.
7. Tạo issue và acceptance criteria.
8. Tạo project foundation.
9. Merge foundation PR.
10. Yêu cầu các thành viên pull `develop`.
11. Tổ chức tích hợp cuối mỗi ngày.
12. Không cho thêm chức năng ngoài MVP khi chưa đánh giá ảnh hưởng.
