# ParkSmart AI

ParkSmart AI là hệ thống demo quản lý và dẫn đường trong bãi xe tầng F1. FastAPI
và PostgreSQL giữ trạng thái authoritative cho bản đồ, ô đỗ, reservation, phiên
đỗ xe và vị trí người dùng. Giao diện Next.js hiển thị trạng thái đó; LangGraph
Agent chỉ gọi các Core Service có cùng quy tắc nghiệp vụ với REST API.

Demo mặc định dùng `USER-001` và `VEHICLE-001`. Khi bật `DEMO_MODE` và
`SIMULATOR_ENABLED`, operator có thể đưa demo về baseline: 40 ô, 39 AVAILABLE,
0 RESERVED, 1 OCCUPIED; chỉ `F1-B03` bị chiếm bởi `SIM-CAR-02`.

## Công nghệ và yêu cầu

- Python 3.11 hoặc 3.12, `uv`
- PostgreSQL 16; cấu hình Docker Compose dùng image `pgvector/pgvector:pg16`
- Node.js/npm tương thích Next.js 16.3
- Docker Desktop nếu dùng PostgreSQL trong Compose
- Chromium của Playwright cho release E2E

Tất cả lệnh dưới đây dùng Windows PowerShell và chạy từ thư mục gốc repository,
trừ khi có ghi chú mở terminal riêng.

## 1. Cấu hình môi trường

```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env.local
notepad .env
notepad frontend\.env.local
uv sync --extra dev
Set-Location frontend
npm ci
Set-Location ..
```

Giữ backend URL trong `frontend/.env.local` ở dạng:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

Điền `LLM_API_KEY` trong `.env` nếu dùng Agent thật. Không commit `.env`,
`frontend/.env.local`, API key hoặc database password.

## 2. Khởi động PostgreSQL

```powershell
docker compose up -d database
docker compose ps database
```

Compose mở PostgreSQL tại `localhost:5432` với database/user/password `parksmart`.
`DATABASE_URL` mặc định trong `.env.example` đã khớp cấu hình này.

## 3. Chạy migration

```powershell
uv run alembic upgrade head
uv run alembic current
```

Migration head của Phase 7 là `20260813_0004`.

## 4. Seed dữ liệu demo idempotent

```powershell
uv run python scripts\seed_demo.py
uv run python scripts\seed_demo.py
```

Lần thứ hai phải báo `0 row(s) created`. Script gọi trực tiếp
`src/core/seed.py` qua async SQLAlchemy session đã cấu hình. Nó chỉ thêm dữ liệu
canonical còn thiếu, không reset trạng thái mutable của slot, reservation hoặc
parking session.

## 5. Khởi động FastAPI

Mở PowerShell thứ nhất tại thư mục gốc:

```powershell
uv run uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Kiểm tra `http://localhost:8000/health` và Swagger UI tại
`http://localhost:8000/docs`.

## 6. Khởi động Next.js

Mở PowerShell thứ hai:

```powershell
Set-Location D:\learn\2026\VinAI\Project\P-152\frontend
npm run dev
```

Mở `http://localhost:3000`. Backend và PostgreSQL phải đang chạy.

## 7. Reset demo một bước

Khi backend đang chạy với `DEMO_MODE=true` và `SIMULATOR_ENABLED=true`:

```powershell
uv run python scripts\reset_demo.py
```

Script chỉ gọi public API `POST /api/v1/simulator/reset`, sau đó kiểm chứng
baseline qua public API. Nó không truy cập hay xóa dữ liệu database trực tiếp.

## 8. Backend tests

```powershell
uv run ruff check src tests scripts
uv run pytest tests\test_core tests\test_api tests\test_agents -q
```

## 9. Frontend lint, test và build

```powershell
Set-Location frontend
npm run lint
npm test
npm run build
Set-Location ..
```

Vitest kiểm tra client API, workflow và UI. `next build` là production build của
Next.js 16.3.

## 10. Playwright release flow

Release E2E dùng Next.js production, FastAPI, PostgreSQL và Core API thật; không
mock parking, recommendation, reservation, session, simulator hoặc routing.

```powershell
docker compose up -d database
Set-Location frontend
npx playwright install chromium
npm run test:e2e
Set-Location ..
```

Runner tạo lại database test riêng `parksmart_e2e`, build frontend, khởi động
stack ở cổng 3100/8100 và chạy happy path ba vòng cùng error path cạnh tranh ô.
Nó không thay đổi database `parksmart` dùng để demo thủ công.

Live Agent E2E là tùy chọn. Lệnh sau đọc key từ `.env` mà không in key ra log:

```powershell
$keyLine = Get-Content .env | Where-Object { $_ -match '^\s*LLM_API_KEY\s*=' } | Select-Object -First 1
$env:LLM_API_KEY = ($keyLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
$env:RUN_LIVE_AGENT_E2E = "1"
Set-Location frontend
npm run test:e2e:live-agent
Set-Location ..
```

## Kiến trúc và an toàn vận hành

- `src/core`: state transitions, recommendation, routing, seed và demo reset.
- `src/api`: REST adapters và middleware tạo/propagate `X-Request-ID`.
- `src/agents`: LangGraph orchestration và tool adapters gọi Core Service.
- `frontend`: React 19/Next.js 16.3 UI đọc trạng thái authoritative.
- `alembic`: lịch sử schema PostgreSQL.

Lỗi frontend hiển thị lời giải thích tiếng Việt, `ApiError.code` và `request_id`
để operator đối chiếu log. Backend log cùng `request_id` tại request boundary,
Agent chat và Agent tool. Hệ thống không log secret, raw prompt, raw tool payload
hoặc internal reasoning.

Checklist phát hành Phase 7 nằm tại
[`docs/PHASE_7_RELEASE_CHECKLIST.md`](docs/PHASE_7_RELEASE_CHECKLIST.md).
