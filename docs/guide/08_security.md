# 08 — Security and Privacy

## 1. Mục tiêu

Bảo vệ:

* Danh tính người dùng.
* Biển số xe.
* Thông tin căn hộ.
* Dữ liệu ra vào.
* Reservation.
* Approval request.
* Secret và access token.
* Agent conversation log.

## 2. Authentication

* Người dùng đăng nhập bằng Supabase Auth.
* Frontend nhận Supabase access token.
* Frontend gửi token bằng Bearer header.
* FastAPI xác minh token.
* FastAPI lấy user ID từ token đã xác minh.
* FastAPI truy vấn `profiles` để lấy ParkSmart role.

Không tin tưởng:

* `user_id` trong request body.
* `role` trong request body.
* Role do LLM cung cấp.
* Route protection phía frontend.

## 3. Application roles

```text
resident
security
admin
```

Quyền phải được kiểm tra tại backend.

### Resident

* Chỉ xem phương tiện và reservation thuộc mình hoặc household được phép.
* Không truy cập Admin API.
* Không cập nhật trạng thái slot trực tiếp.

### Security

* Xem và xử lý xe khách.
* Xem trạng thái bãi xe.
* Không duyệt approval vượt định mức.

### Admin

* Xử lý approval.
* Quản lý trạng thái slot.
* Xem audit log được phép.

## 4. Secret management

Không commit:

```text
.env
OPENAI_API_KEY
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_JWT_SECRET
DATABASE_URL có mật khẩu
Access token
Refresh token
```

Frontend chỉ được sử dụng:

```text
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
NEXT_PUBLIC_API_URL
```

Frontend không được sử dụng:

```text
SUPABASE_SERVICE_ROLE_KEY
OPENAI_API_KEY
DATABASE_URL
```

## 5. Dữ liệu biển số

Biển số đầy đủ chỉ được trả khi nghiệp vụ thực sự cần.

Trong log, biển số phải được che.

Ví dụ:

```text
30A-***.45
```

Không ghi biển số thật trong:

* AI usage log.
* Console log không kiểm soát.
* Error message.
* Public demo dataset.
* Prompt gửi LLM nếu không cần thiết.

## 6. LLM data minimization

Không gửi cho LLM:

* Access token.
* Refresh token.
* Cookie.
* Password.
* Audit log đầy đủ.
* Lịch sử ra vào đầy đủ.
* Thông tin người dùng khác.
* Database connection string.
* Supabase service role key.

Agent tool chỉ trả các trường cần thiết cho việc tạo câu trả lời.

## 7. RAG security

Không đưa vào vector database:

* Thông tin cá nhân.
* Biển số thật.
* Lịch sử ra vào.
* Reservation.
* Approval.
* Audit log.
* Access token.

Vector database chỉ lưu tài liệu nội quy và kiến thức chung.

## 8. AI logging security

Các script trong `scripts/` phải xóa hoặc che:

```text
Authorization
Cookie
access_token
refresh_token
OPENAI_API_KEY
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_JWT_SECRET
DATABASE_URL
```

`.ai-log/raw/` và `.ai-log/private/` phải nằm trong `.gitignore`.

## 9. Audit logging

Phải ghi audit log cho:

* Đăng ký phương tiện.
* Vô hiệu hóa phương tiện.
* Tạo hoặc hủy reservation.
* Check-in/check-out xe khách.
* Approve/reject yêu cầu.
* Thay đổi trạng thái slot.
* Thay đổi policy.

Audit log phải ghi:

* Actor ID.
* Actor role.
* Action.
* Resource type.
* Resource ID.
* Timestamp.
* Payload đã che dữ liệu nhạy cảm.

## 10. Demo data

* Không sử dụng thông tin cư dân thật.
* Không sử dụng biển số thật của thành viên.
* Không sử dụng email cá nhân.
* Tất cả tài khoản phải là tài khoản demo.
* Reset dữ liệu demo được trước buổi trình bày.
