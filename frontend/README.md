# ParkSmart AI frontend

Giao diện React 19 và Next.js 16.3 hiển thị dữ liệu authoritative từ ParkSmart
FastAPI. Bản đồ, trạng thái slot, recommendation, reservation, route, parking
session và Agent chat đều dùng backend; frontend không tự chuyển trạng thái ô
hoặc tự tính đường đi.

Production public beta chạy trên Vercel Hobby và gọi FastAPI image-backed trên Render.
`BackendReadinessGate` đợi `/api/v1/health/database` thành công trước khi mount
`AuthProvider`, nhờ đó Render cold start không bị diễn giải thành lỗi đăng nhập. Voice bị
tắt; Agent chat, privacy disclosure và user/admin flows vẫn hoạt động.

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
NEXT_PUBLIC_SUPABASE_URL=https://<project>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<public key>
NEXT_PUBLIC_DEMO_MODE=false
NEXT_PUBLIC_AGENT_ENABLED=true
NEXT_PUBLIC_SPEECH_ENABLED=false
NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL=<real monitored email>
```

Các biến `NEXT_PUBLIC_*` là build-time values và xuất hiện trong browser bundle. Không đặt
LLM key, Supabase service-role key hoặc secret backend trong các biến này. Sau khi thay cờ,
URL hoặc privacy email, phải build/deploy Vercel lại.

## Public beta deployment

Từ thư mục `frontend`, liên kết project một lần rồi deploy source local bằng Vercel CLI:

```bash
npx vercel link
npx vercel env ls production
npx vercel deploy --prod --logs
```

Production cần thêm `PARKSMART_BACKEND_ORIGIN=<render-origin>` cho Next.js rewrite và
`NEXT_PUBLIC_API_BASE_URL=<render-origin>/api/v1`. Supabase Auth `Site URL` và redirect
allowlist phải dùng production Vercel origin; backend `CORS_ORIGINS` cũng phải khớp origin
đó. Không commit `.vercel/`, `.env.local` hoặc `VERCEL_OIDC_TOKEN`.

Supabase Auth dùng `sessionStorage` và storage key riêng cho từng tab. Nhờ đó một tab
có thể đăng nhập user và tab khác đăng nhập admin mà không ghi đè session. Đóng tab sẽ
kết thúc session của tab đó; hãy mở tab mới thay vì duplicate tab đã đăng nhập.

Sau khi PostgreSQL, migration, seed và FastAPI đã sẵn sàng theo README gốc, mở
một PowerShell riêng:

```powershell
Set-Location D:\learn\2026\VinAI\Project\P-152\frontend
npm run dev
```

Mở `http://localhost:3000`.

Report xe đỗ sai dùng luồng xác nhận ba bước: chọn ô/lý do, bổ sung biển số-mô tả-ảnh
tùy chọn, rồi bấm nút gửi riêng. Popup có vùng cuộn nội bộ và submit dock sticky trên
màn hình thấp. Dashboard `/admin` không hiển thị simulator controls; click slot mở panel
chi tiết và nút **Đóng ×** bỏ cả panel lẫn highlight.

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
