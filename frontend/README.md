# ParkSmart AI frontend

Giao diện React 19 và Next.js 16.3 hiển thị dữ liệu authoritative từ ParkSmart
FastAPI. Bản đồ, trạng thái slot, recommendation, reservation, route, parking
session và Agent chat đều dùng backend; frontend không tự chuyển trạng thái ô
hoặc tự tính đường đi.

## Chạy giao diện trên Windows PowerShell

Chuẩn bị một lần từ thư mục gốc repository:

```powershell
Copy-Item frontend\.env.example frontend\.env.local
Set-Location frontend
npm ci
Set-Location ..
```

`frontend/.env.local` cần chứa:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

Sau khi PostgreSQL, migration, seed và FastAPI đã sẵn sàng theo README gốc, mở
một PowerShell riêng:

```powershell
Set-Location D:\learn\2026\VinAI\Project\P-152\frontend
npm run dev
```

Mở `http://localhost:3000`.

## Quality gates

```powershell
Set-Location frontend
npm run lint
npm test
npm run build
```

`npm test` chạy Vitest một lần, không bật watch mode.

## Playwright trên stack thật

Yêu cầu Docker/PostgreSQL tại `localhost:5432`, Python dependencies từ `uv
sync --extra dev`, Chromium Playwright và hai cổng trống `3100`, `8100`.

```powershell
docker compose up -d database
Set-Location frontend
npx playwright install chromium
npm run test:e2e
```

Runner dùng database riêng `parksmart_e2e`, production Next.js, FastAPI và Core
API thật. Nó chạy happy path ba lần liên tiếp và error path `SLOT_NOT_AVAILABLE`.
Không endpoint nghiệp vụ nào bị mock. Có thể override bằng
`E2E_DATABASE_URL`, `E2E_FRONTEND_URL`, `E2E_BACKEND_URL` và `E2E_API_URL`.

Live Agent test là opt-in:

```powershell
Set-Location ..
$keyLine = Get-Content .env | Where-Object { $_ -match '^\s*LLM_API_KEY\s*=' } | Select-Object -First 1
$env:LLM_API_KEY = ($keyLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
$env:RUN_LIVE_AGENT_E2E = "1"
Set-Location frontend
npm run test:e2e:live-agent
```

Live test gọi Agent endpoint thật và kiểm tra state transition thay vì khớp
nguyên văn LLM. Trace/video chỉ được giữ khi retry; screenshot chỉ khi thất bại.
`test-results/` và `playwright-report/` không được commit.

Hướng dẫn đầy đủ cho environment, PostgreSQL, Alembic, seed, FastAPI, reset demo
và backend tests nằm trong [`../README.md`](../README.md).
