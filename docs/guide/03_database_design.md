---
title: "ParkSmart AI — Thiết kế Database"
owner: "Đoàn"
status: "Draft"
---

# 03 — Database Design

## 1. File này để làm gì?

File này là bản vẽ dữ liệu của ParkSmart AI. Mọi người đọc file này để biết:

- Cần lưu những thông tin gì.
- Mỗi thông tin nằm ở bảng nào.
- Các bảng liên quan với nhau ra sao.
- Dữ liệu nào không được trùng hoặc không được sửa tùy ý.


## 2. Các từ dùng chung

| Từ | Nghĩa |
|---|---|
| `resident` | Cư dân |
| `security` | Bảo vệ |
| `admin` | Ban quản lý |
| `profile` | Hồ sơ ParkSmart của một người đã đăng nhập Supabase |
| `household` | Một căn hộ/hộ dân |
| `slot` | Một vị trí đỗ xe |
| `reservation` | Lần đặt một slot |

## 3. Các bảng cần có

### Nhóm người dùng

| Bảng | Dùng để lưu | Thông tin chính |
|---|---|---|
| `profiles` | Hồ sơ người dùng ParkSmart | `id`, `email`, `full_name`, `app_role` |
| `households` | Căn hộ/hộ dân | `id`, `code`, `name`, `vehicle_limit` |
| `household_members` | Người nào thuộc căn hộ nào | `household_id`, `profile_id`, `is_active` |

**Quy tắc quan trọng:** `profiles.id` phải chính là ID user do Supabase Auth tạo.
Không tự tạo một user ID khác.

### Nhóm xe và chỗ đỗ

| Bảng | Dùng để lưu | Thông tin chính |
|---|---|---|
| `vehicles` | Xe của cư dân | `id`, `household_id`, `owner_profile_id`, `plate_number`, `vehicle_type`, `status` |
| `parking_cards` | Thẻ xe, nếu dùng | `id`, `vehicle_id`, `card_code`, `status` |
| `parking_areas` | Tầng/khu gửi xe | `id`, `code`, `floor`, `zone`, `vehicle_type` |
| `parking_slots` | Từng ô đỗ xe | `id`, `parking_area_id`, `code`, `vehicle_type`, `status` |
| `reservations` | Lịch sử đặt chỗ | `id`, `vehicle_id`, `parking_slot_id`, `status`, `starts_at`, `expires_at` |

### Nhóm nghiệp vụ khác

| Bảng | Dùng để lưu | Thông tin chính |
|---|---|---|
| `guest_registrations` | Xe khách do cư dân đăng ký | `id`, `resident_profile_id`, `plate_number`, `valid_from`, `valid_until`, `status` |
| `approval_requests` | Yêu cầu xe vượt định mức cần BQL duyệt | `id`, `vehicle_id`, `requester_profile_id`, `status`, `reviewed_by_profile_id` |
| `notifications` | Thông báo cho người dùng | `id`, `profile_id`, `title`, `body`, `is_read` |
| `audit_logs` | Nhật ký hành động quan trọng | `id`, `actor_profile_id`, `action`, `resource_type`, `resource_id`, `created_at` |

### Nhóm AI/RAG

| Bảng | Dùng để lưu | Thông tin chính |
|---|---|---|
| `parking_policies` | Nội quy, chính sách gửi xe | `id`, `title`, `content`, `version`, `is_active` |
| `knowledge_chunks` | Các đoạn nội quy để RAG tìm kiếm | `id`, `policy_id`, `content`, `embedding` |
| `agent_messages` | Lịch sử chat của người dùng | `id`, `conversation_id`, `profile_id`, `role`, `content`, `created_at` |

## 4. Các bảng liên quan với nhau thế nào?

```text
Supabase user
    └── profiles
          └── household_members ── households
                                      └── vehicles
                                            └── parking_cards

vehicles ── reservations ── parking_slots ── parking_areas

profiles ── guest_registrations
profiles ── approval_requests ── vehicles
profiles ── notifications
profiles ── audit_logs

parking_policies ── knowledge_chunks
profiles ── agent_messages
```

Ví dụ: một cư dân đăng nhập → có một `profile` → thuộc một `household` →
đăng ký `vehicle` → dùng xe đó để tạo `reservation` cho một `parking_slot`.

## 5. Trạng thái phải dùng đúng tên

| Dữ liệu | Trạng thái được phép |
|---|---|
| Role người dùng | `resident`, `security`, `admin` |
| Xe | `pending`, `active`, `rejected`, `blocked`, `inactive` |
| Slot | `available`, `reserved`, `occupied`, `maintenance` |
| Reservation | `active`, `used`, `cancelled`, `expired` |
| Approval | `pending`, `approved`, `rejected`, `cancelled` |
| Xe khách | `registered`, `checked_in`, `checked_out`, `expired`, `cancelled` |

Không tự đổi thành những tên như `done`, `confirmed` hay `waiting` vì cả team
sẽ dễ hiểu khác nhau.

## 6. Các quy tắc database quan trọng

1. Một biển số chỉ có một xe trong hệ thống.
2. Một xe chỉ có một reservation đang `active`.
3. Một slot chỉ có một reservation đang `active`.
4. Một reservation chỉ được tạo khi xe `active` và slot `available`.
5. `valid_until` của xe khách phải lớn hơn `valid_from`.
6. Approval đã xử lý không được xử lý lại.
7. Không xóa lịch sử reservation, approval hoặc audit log; chỉ đổi status khi cần.

## 7. Thứ tự code sau khi Leader duyệt

| Giai đoạn | Đoàn cần làm |
|---|---|
| Ngày 2–4 | Tạo bảng `profiles`, kết nối PostgreSQL, Supabase Auth, API `/me` |
| Ngày 4–7 | Tạo bảng/service cho vehicle, parking, reservation |
| Ngày 6–10 | Guest, approval, notification, audit log |
| Sau đó | Policy và RAG cùng Phú Thành |

## 8. Dữ liệu cần bảo vệ

- Không ghi API key, token hoặc mật khẩu vào database/log/document.
- Không dùng biển số, email hoặc tên thật của thành viên trong dữ liệu demo.
- Không đưa reservation, thông tin xe hoặc thông tin cư dân vào RAG.
- Nếu log biển số, phải che bớt, ví dụ: `30A-***.45`.

