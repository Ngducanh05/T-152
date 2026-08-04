---
title: "ParkSmart AI — Luật Nghiệp vụ"
owner: "Đoàn"
status: "Draft"
---

# 05 — Business Rules

## 1. File này để làm gì?

File này ghi các luật ParkSmart phải luôn tuân theo. Khi code:

- Route FastAPI gọi service, không tự xử lý luật dài.
- Service kiểm tra luật.
- Agent gọi tool → tool gọi service; Agent không tự bỏ qua luật.
- Mỗi luật phải có test thành công và test thất bại.

## 2. Đăng nhập và quyền

### BR-AUTH-001 — Phải đăng nhập mới dùng API riêng tư

- **Khi nào:** User gọi API cần tài khoản, như `/me`, xe hoặc reservation.
- **Hệ thống làm gì:** Đọc Bearer token do Supabase cấp; lấy ID user từ token;
  sau đó lấy role ParkSmart từ bảng `profiles`.
- **Nếu sai:** Không có token → `AUTH_REQUIRED`. Token sai/hết hạn → `INVALID_TOKEN`.
- **Test:** không gửi token; gửi token sai; gửi token đúng.

### BR-AUTH-002 — Không tin `user_id` hoặc `role` từ frontend

- **Khi nào:** Frontend gửi body có `user_id` hoặc `role`.
- **Hệ thống làm gì:** Bỏ qua các giá trị đó; luôn dùng user/role đã xác minh ở backend.
- **Nếu sai quyền:** Trả `ROLE_FORBIDDEN` hoặc `RESOURCE_FORBIDDEN`.
- **Test:** resident thử gọi API admin; user thử sửa dữ liệu của người khác.

## 3. Xe

### BR-VEH-001 — Không được trùng biển số

- **Khi nào:** Đăng ký hoặc sửa xe.
- **Hệ thống làm gì:** Kiểm tra biển số đã có trong hệ thống chưa.
- **Nếu trùng:** Trả `DUPLICATE_PLATE_NUMBER`.
- **Test:** đăng ký hai xe cùng biển số; sửa xe thành biển số của xe khác.

### BR-VEH-002 — Xe vượt định mức phải chờ admin duyệt

- **Khi nào:** Căn hộ đã đủ số xe được phép nhưng cư dân đăng ký thêm xe.
- **Hệ thống làm gì:** Tạo xe `pending` và một approval request `pending`.
- **Kết quả:** Xe chưa được đặt chỗ cho tới khi admin duyệt.
- **Test:** dưới định mức thì xe `active`; vượt định mức thì xe `pending`.

### BR-VEH-003 — Chỉ xe active mới được đặt chỗ

- **Khi nào:** Tạo reservation.
- **Hệ thống làm gì:** Kiểm tra xe có status `active`.
- **Nếu không:** Trả `VEHICLE_NOT_ACTIVE`.
- **Test:** xe pending, rejected, blocked, inactive đều không đặt chỗ được.

## 4. Slot và đặt chỗ

### BR-SLOT-001 — User không được tự đổi trạng thái slot

- **Khi nào:** Có yêu cầu đổi slot thành available/reserved/occupied.
- **Hệ thống làm gì:** Chỉ Slot Simulator, admin hoặc service nội bộ được đổi.
- **Nếu user không có quyền:** Trả `ROLE_FORBIDDEN`.
- **Test:** resident thử đổi slot; simulator đổi slot thành công.

### BR-RES-001 — Chỉ slot available mới đặt được

- **Khi nào:** Cư dân chọn một slot để đặt.
- **Hệ thống làm gì:** Kiểm tra xe active, slot available và xe thuộc quyền sử dụng của user.
- **Nếu sai:** Trả `VEHICLE_NOT_ACTIVE`, `RESOURCE_FORBIDDEN` hoặc `SLOT_NOT_AVAILABLE`.
- **Test:** slot available; slot occupied; xe của người khác; xe pending.

### BR-RES-002 — Không đặt trùng

- **Khi nào:** Tạo reservation.
- **Hệ thống làm gì:** Một xe chỉ có một reservation active; một slot chỉ có một
  reservation active.
- **Nếu trùng:** Xe đã đặt → `ACTIVE_RESERVATION_EXISTS`; slot đã có người đặt
  → `SLOT_NOT_AVAILABLE`.
- **Test:** cùng xe đặt hai lần; hai người cùng đặt một slot.

### BR-RES-003 — Đặt/hủy chỗ phải làm trọn vẹn

- **Khi nào:** Tạo, hủy hoặc hết hạn reservation.
- **Hệ thống làm gì:** Tạo reservation và đổi slot thành `reserved` trong cùng
  một transaction. Khi hủy/hết hạn, slot trở về `available` nếu nó chưa
  `occupied` hoặc `maintenance`.
- **Nếu một bước lỗi:** Rollback toàn bộ, không để dữ liệu nửa đúng nửa sai.
- **Test:** giả lập lỗi khi đổi status; hai request cùng lúc chỉ một request thắng.

## 5. Xe khách

### BR-GUEST-001 — Thời gian xe khách phải hợp lệ

- **Khi nào:** Cư dân đăng ký xe khách.
- **Hệ thống làm gì:** Kiểm tra `valid_until` sau `valid_from`.
- **Nếu sai:** Trả validation error.
- **Test:** thời gian đúng; thời gian bằng nhau; thời gian kết thúc trước khi bắt đầu.

### BR-GUEST-002 — Chỉ bảo vệ check-in/check-out

- **Khi nào:** Check-in hoặc check-out xe khách.
- **Hệ thống làm gì:** Chỉ role `security` được thao tác; xe phải còn trong thời
  gian hiệu lực và chưa ở trạng thái không hợp lệ.
- **Nếu sai:** Trả `ROLE_FORBIDDEN`, `GUEST_REGISTRATION_EXPIRED`,
  `GUEST_ALREADY_CHECKED_IN` hoặc `GUEST_ALREADY_CHECKED_OUT`.
- **Test:** resident check-in; guest hết hạn; check-in hai lần; check-out hai lần.

## 6. Approval

### BR-APP-001 — Chỉ admin được duyệt hoặc từ chối

- **Khi nào:** Xử lý approval request.
- **Hệ thống làm gì:** Chỉ `admin` xử lý request đang `pending`.
- **Nếu sai:** Trả `ROLE_FORBIDDEN` hoặc `APPROVAL_ALREADY_PROCESSED`.
- **Test:** resident/security duyệt; admin duyệt; duyệt lại request cũ.

### BR-APP-002 — Duyệt xe phải cập nhật đủ thông tin

- **Khi nào:** Admin approve/reject xe vượt định mức.
- **Hệ thống làm gì:** Cập nhật approval, đổi vehicle thành `active` hoặc
  `rejected`, tạo notification và audit log trong cùng transaction.
- **Nếu một bước lỗi:** Rollback; không báo duyệt thành công.
- **Test:** approve; reject; lỗi khi tạo notification.

## 7. Agent AI và RAG

### BR-AI-001 — Agent không tự truy cập database

- **Khi nào:** User chat để đặt slot hoặc đăng ký xe.
- **Hệ thống làm gì:** Agent gọi tool; tool gọi service; service kiểm tra rule và
  truy cập database.
- **Không được:** Agent sinh SQL, tự kiểm tra quyền hoặc tự tạo dữ liệu slot.
- **Test:** Agent chỉ dùng tool; tool lỗi thì Agent không nói là thành công.

### BR-AI-002 — Agent chỉ báo thành công khi tool báo thành công

- **Khi nào:** Tool trả kết quả.
- **Hệ thống làm gì:** Chỉ nói “đặt chỗ thành công” khi tool trả `success=true`.
- **Nếu tool lỗi:** Nói rõ không thể hoàn thành; không bịa kết quả.
- **Test:** tool thành công; slot không còn; tool timeout.

### BR-AI-003 — RAG chỉ trả lời nội quy

- **Khi nào:** User hỏi nội quy hoặc hỏi dữ liệu hiện tại.
- **Hệ thống làm gì:** RAG chỉ tìm nội quy/chính sách. Hỏi slot, xe,
  reservation hoặc approval thì phải gọi tool/service realtime.
- **Nếu không có nội quy phù hợp:** Nói chưa đủ thông tin hoặc trả
  `RAG_CONTEXT_NOT_FOUND`.
- **Test:** hỏi nội quy; hỏi slot trống; không có context.

### BR-AI-004 — Agent không được duyệt yêu cầu

- **Khi nào:** User hỏi “hãy duyệt xe vượt định mức cho tôi”.
- **Hệ thống làm gì:** Agent chỉ tạo hoặc tra cứu request, rồi báo chờ admin.
- **Test:** Agent không có tool approve/reject và không khẳng định đã duyệt.

## 8. Bảo mật và audit log

### BR-SEC-001 — Không làm lộ dữ liệu nhạy cảm

- Không ghi API key, access token, refresh token, mật khẩu hoặc database URL có
  password vào log, prompt hay tài liệu.
- Không dùng dữ liệu thật của cư dân trong demo.
- Nếu log biển số, phải che bớt: `30A-***.45`.

### BR-SEC-002 — Các hành động quan trọng phải có audit log

- **Cần log:** đăng ký/vô hiệu hóa xe, đặt/hủy chỗ, check-in/out xe khách,
  duyệt/từ chối approval và đổi trạng thái slot.
- **Audit log cần có:** ai làm, role gì, làm hành động gì, với dữ liệu nào và lúc
  nào.
- **Không được log:** token, secret hoặc biển số đầy đủ.

## 9. Checklist trước khi code

- [ ] Leader duyệt các bảng, trạng thái và quan hệ trong file database design.
- [ ] Leader duyệt các business rules trong file này.
- [ ] Quang Thành xác nhận frontend dùng đúng role và API contract.
- [ ] Phú Thành xác nhận Agent tool sẽ gọi service, không gọi database trực tiếp.
- [ ] Sau đó Đoàn mới tạo migration, service và test.

