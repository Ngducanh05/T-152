# ParkSmart AI — Frontend demo

Giao diện demo Next.js cho luồng MVP của ParkSmart AI. Toàn bộ dữ liệu trong bản demo được giữ ở phía trình duyệt để có thể trình diễn độc lập với backend.

## Chạy dự án

```bash
cd frontend
npm install
npm run dev
```

Mở `http://localhost:3000`.

## Luồng demo gợi ý

1. Chọn **Vị trí của bạn**, chọn một `node_id` và xác nhận vị trí hiện tại.
2. Chọn tiêu chí EV/thang máy và nhấn **Tìm ô tốt nhất**.
3. Nhấn **Hiện đường đi**, sau đó **Xác nhận đã đỗ**.
4. Chọn **Xe của tôi ở đâu?** để tạo đường quay lại xe.
5. Mở **Mô phỏng** để đổi trạng thái ô hoặc đặt lại kịch bản.

Đây là frontend demo. Khi tích hợp thật, các thao tác trạng thái, scoring, routing và parking session phải gọi backend service tương ứng; Agent không được cập nhật dữ liệu trực tiếp.
