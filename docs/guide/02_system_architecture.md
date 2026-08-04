# 02 — System Architecture

## 1. Thông tin tài liệu

* Project: ParkSmart AI
* Owner: Leader
* Reviewers: Đoàn, Phú Thành
* Status: Approved for MVP

## 2. Kiến trúc tổng thể

ParkSmart AI sử dụng kiến trúc modular monolith.

Các thành phần chính:

* Next.js frontend.
* Supabase Authentication.
* FastAPI backend.
* LangGraph Agent.
* Service layer.
* PostgreSQL.
* pgvector.
* Supabase Realtime.
* Slot Simulator.

## 3. Sơ đồ thành phần

```text
Next.js Frontend
       |
       | HTTPS REST + Bearer Token
       v
FastAPI Backend
       |
       +-- Authentication and Authorization
       |
       +-- API Routes
       |
       +-- Business Services
       |       |
       |       +-- PostgreSQL
       |       +-- SlotProvider
       |       +-- Notification
       |       +-- Audit log
       |
       +-- LangGraph Agent
               |
               +-- Agent Nodes
               +-- Agent Tools
               +-- RAG Service
                       |
                       +-- pgvector
```

## 4. Luồng API thông thường

```text
Frontend
→ FastAPI Route
→ Pydantic Validation
→ Authentication
→ Authorization
→ Business Service
→ Business Rules
→ Database
→ Pydantic Response
→ Frontend
```

Ví dụ luồng đặt chỗ:

```text
POST /api/v1/reservations
→ Xác minh JWT
→ Lấy current user
→ Kiểm tra vehicle ownership
→ Kiểm tra vehicle active
→ Kiểm tra slot available
→ Tạo reservation trong transaction
→ Cập nhật slot thành reserved
→ Trả kết quả
```

## 5. Luồng AI Agent

```text
User message
→ POST /api/v1/agent/chat
→ Backend lấy user từ JWT
→ LangGraph nhận user context
→ Classify intent
→ Chọn Agent tool
→ Agent tool gọi Business Service
→ Service kiểm tra business rule
→ Service truy vấn database hoặc RAG
→ Tool trả structured result
→ Agent tạo câu trả lời
```

## 6. Luồng HITL

```text
Resident yêu cầu đăng ký thêm xe
→ Vehicle service kiểm tra định mức
→ Đạt hoặc vượt định mức
→ Tạo vehicle status=pending
→ Tạo approval request status=pending
→ Admin xem yêu cầu
→ Admin approve hoặc reject
→ Service cập nhật vehicle
→ Tạo notification
→ Ghi audit log
```

Agent không tự phê duyệt yêu cầu.

## 7. Luồng xác thực

```text
User login
→ Supabase Auth
→ Supabase access token
→ Frontend gửi Bearer token
→ FastAPI xác minh token
→ FastAPI lấy Supabase user ID
→ FastAPI truy vấn profiles
→ Xác định app_role
```

Phân biệt:

```text
Supabase authentication role:
authenticated

ParkSmart application role:
resident | security | admin
```

## 8. Luồng dữ liệu realtime

```text
Database record changes
→ Supabase Realtime
→ Next.js subscription
→ UI refresh
```

Realtime dùng cho:

* parking_slots
* reservations
* approval_requests
* notifications

Realtime không thay thế kiểm tra business rule ở backend.

## 9. Quy định source code

### `src/api/`

* Nhận và validate request.
* Xác thực và phân quyền.
* Gọi service.
* Trả response.

Không chứa business logic dài.

### `src/services/`

* Chứa business logic.
* Quản lý transaction.
* Truy cập database.
* Áp dụng rule.
* Ghi audit log.

### `src/agents/`

* Chứa LangGraph.
* Chứa Agent state.
* Chứa nodes.
* Chứa tools.

Agent tool phải gọi service.

### `src/models/`

* Chỉ chứa Pydantic schemas.
* Không đặt SQLAlchemy ORM mặc định trong thư mục này.

## 10. Nguyên tắc bắt buộc

1. Database là nguồn sự thật cho dữ liệu nghiệp vụ.
2. LLM không được truy cập database trực tiếp.
3. LLM không được tự sinh và chạy SQL.
4. Agent không được tự quyết định authorization.
5. Agent tool không được lặp lại business rule.
6. RAG không được dùng cho dữ liệu realtime.
7. Frontend không được chứa service role key.
8. Router không chứa transaction nghiệp vụ.
9. Mọi thao tác ghi dữ liệu phải đi qua service.
10. Các thao tác nhạy cảm phải có audit log.

## 11. Deployment

* Frontend: Vercel.
* Backend: Railway hoặc Docker-compatible platform.
* Database và Auth: Supabase.
* Local: Docker Compose.
