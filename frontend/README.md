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
