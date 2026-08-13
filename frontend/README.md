# ParkSmart AI frontend

Ứng dụng Next.js 16.3 và React 19 hiển thị dữ liệu authoritative từ ParkSmart
FastAPI. Bản đồ, trạng thái slot, recommendation, reservation, route, parking
session và Agent chat đều dùng API backend; frontend không tự tính route hoặc tự
chuyển trạng thái slot.

## Yêu cầu

- Node.js và npm tương thích với Next.js 16.3.
- ParkSmart FastAPI đang chạy và cung cấp các endpoint dưới `/api/v1`.

Tạo `frontend/.env.local` từ `.env.example` và đặt URL API:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

## Khởi động

Khởi động backend từ thư mục repository theo hướng dẫn chính của dự án. Sau đó:

```bash
cd frontend
npm install
npm run dev
```

Mở `http://localhost:3000`.

## Kiểm tra

```bash
npm run lint
npm run test
npm run test:ci
npm run build
```

`npm run test` và `npm run test:ci` đều chạy Vitest đúng một lần, không bật watch
mode. `test:ci` dùng reporter mặc định rõ ràng cho môi trường CI.

## Playwright E2E trên stack thật

Bộ E2E mặc định sử dụng production Next.js, FastAPI, PostgreSQL và các Core API
thật. Test không mock parking, recommendation, reservation, session, simulator
hoặc routing endpoint.

Yêu cầu trước khi chạy:

- Docker đang hoạt động và PostgreSQL ParkSmart khả dụng tại `localhost:5432`.
- Python dependencies đã được cài bằng `uv sync`.
- PostgreSQL user có quyền tạo/xóa database test. Mặc định runner tự tạo lại
  database riêng `parksmart_e2e`; override bằng `E2E_DATABASE_URL` nếu cần.
- Chromium của Playwright đã được cài.
- Hai cổng E2E mặc định `3100` và `8100` đang trống.

Từ thư mục repository:

```powershell
docker compose up -d database
cd frontend
npx playwright install chromium
npm run test:e2e
```

`npm run test:e2e` tạo mới database E2E và canonical seed, build frontend với
đúng backend origin, khởi động FastAPI và `next start`, sau đó để Playwright
health-check stack rồi chạy happy path ba lần liên tiếp và conflict path.
Mỗi iteration bắt đầu bằng public `POST /api/v1/simulator/reset` qua nút
**Đặt lại demo**. Có thể override địa chỉ bằng `E2E_FRONTEND_URL`,
`E2E_BACKEND_URL` và `E2E_API_URL`.

Live Agent test là opt-in và không chạy trong release flow mặc định:

```powershell
$env:RUN_LIVE_AGENT_E2E="1"
$env:LLM_API_KEY="your-key"
npm run test:e2e:live-agent
```

Live test gọi Agent endpoint thật và kiểm tra tool/state thay vì so khớp nguyên
văn câu trả lời của LLM. Trace và video chỉ được giữ ở lần retry; screenshot chỉ
được giữ khi thất bại. `test-results/` và `playwright-report/` đã được ignore.
