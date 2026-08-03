



## 1. Brief (Tóm tắt tổng quan dự án)

  * **Tên dự án:** ParkSmart AI – Agent Quản lý và Điều phối Gửi xe Thông minh.
  * **Nguồn lực:** Thực hiện trong 2 tuần với đội ngũ 4 thành viên (Leader, Đoàn, Quang Thành, Phú Thành). Mục tiêu là ra được một MVP có thể chạy, deploy và demo.
  * **Bài toán cần giải quyết:** Giải quyết tình trạng hầm gửi xe quá tải, cư dân/khách không biết vị trí trống, đăng ký thủ công, và tình trạng đăng ký vượt định mức.
  * **Giải pháp:** Cung cấp AI Agent hỗ trợ quản lý, đăng ký, tra cứu và đặt chỗ gửi xe thông minh.

## 2. PRD (Product Requirements Document - Tài liệu đặc tả yêu cầu sản phẩm)

  * **Phân quyền:** Hệ thống chia làm 3 vai trò chính: cư dân (`resident`), bảo vệ (`security`), và Ban quản lý (`admin`).
  * **Tính năng bắt buộc:** Quản lý phương tiện, quản lý chỗ đỗ (xem, đặt, hủy slot), đăng ký xe khách, và luồng duyệt yêu cầu thủ công (Human-in-the-Loop) khi đăng ký xe vượt định mức.
  * **AI Agent & RAG:** AI Agent hỗ trợ các ý định (intent) như kiểm tra chỗ trống, đặt/hủy chỗ, đăng ký xe... kết hợp RAG để trả lời về nội quy, chính sách.
  * **Quy tắc nghiệp vụ (Business Rules):** Các quy định chặt chẽ như BR-RES-004 (một slot chỉ có một reservation active), BR-VEH-004 (xe vượt định mức phải chờ BQL duyệt), v.v.
  * **Giới hạn MVP:** Không làm camera nhận diện biển số thật, thanh toán, app mobile riêng hay bản đồ 3D.

## 3. Wireframe/UI Flow (Cấu trúc giao diện và luồng người dùng)


  * **Công nghệ:** Sử dụng Next.js, giao diện có thể lưu ở repo riêng hoặc được bổ sung sau.
  * **Các màn hình/UI Component chính:** Cần có màn hình Đăng nhập, Resident Dashboard (cho cư dân), Security Dashboard (cho bảo vệ), Admin Dashboard (cho BQL duyệt yêu cầu), Parking Map (sơ đồ bãi xe dạng grid 2D), Agent Chat, và hệ thống Notifications.
  * **Luồng tương tác:** Giao diện phải phản hồi Realtime (thời gian thực) khi trạng thái slot thay đổi, khi có người đặt/hủy chỗ, hoặc khi Ban quản lý duyệt/từ chối yêu cầu.

## 4. Github Repo AI Log Setup (Thiết lập lưu trữ nhật ký AI trên Github Repository)

  * **Cấu trúc lưu trữ:** Dự án bố trí sẵn thư mục `scripts/` chứa các file như `log_hook.py`, `submit_log.py`, `setup_hooks.sh` để thiết lập cơ chế tự động ghi log.
  * **Thư mục log:** Các nhật ký sử dụng AI sẽ được sinh tự động và lưu vào thư mục `.ai-log/`.
  * **Cấu hình công cụ:** Có các thư mục ẩn riêng cho từng tool như `.claude/`, `.codex/`, `.cursor/`, `.gemini/` để chứa rules nhắc nhở AI tuân thủ bối cảnh dự án.
  * **Quy tắc bảo mật nghiêm ngặt:** Các AI logging hooks bắt buộc phải tự động lọc và KHÔNG ĐƯỢC LƯU các thông tin nhạy cảm như: API Key, access token, mật khẩu database, biển số thật chưa che, hay dữ liệu cá nhân thật của cư dân.
