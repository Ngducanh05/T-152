# ParkSmart AI Production Admin Provisioning

Tài liệu này là quy trình cấp và thu hồi quyền admin cho **public beta
production**. Quy trình development/demo hiện có vẫn giữ nguyên và không được dùng
để cấp quyền production.

ParkSmart chỉ tin cậy `public.profiles.app_role`. Role trong Supabase
`user_metadata` hoặc `app_metadata` không cấp quyền admin cho ParkSmart.

## Nguyên tắc an toàn

- Dùng một tài khoản riêng chỉ dành cho công việc admin. Không dùng tài khoản này
  cho luồng tìm chỗ, giữ chỗ hoặc đỗ xe hằng ngày.
- Không thêm hoặc sửa role qua frontend, anon key hay browser console.
- Không sửa `user_metadata.role`, `user_metadata.app_role`, `app_metadata.role`
  hoặc `app_metadata.app_role` để cấp quyền ParkSmart.
- Chỉ operator có quyền quản trị database mới được chạy SQL trong Supabase SQL
  Editor.
- Production phải có `DEMO_MODE=false` và `SIMULATOR_ENABLED=false`.
- Không commit email admin thật vào repository và không đưa email đó vào public
  issue, public log, chat transcript hoặc tài liệu có quyền truy cập rộng.
- Protected admin provisioning audit record được phép lưu email admin vì đây là
  identifier cần thiết để chứng minh account nào được promotion hoặc revoke. Audit
  record phải giới hạn quyền truy cập và chỉ giữ dữ liệu tối thiểu: thời gian,
  operator, email admin, hành động, số row thay đổi và kết quả xác minh.
- Password, access token, refresh token, API key, `DATABASE_URL` và service-role
  key tuyệt đối không được ghi trong bất kỳ audit record, log hoặc ticket nào.
- Mọi câu lệnh bên dưới dùng placeholder `<ADMIN_EMAIL>`. Supabase SQL Editor cần
  email thật khi operator thay placeholder để thực hiện quy trình, nhưng không sao
  chép query hoặc result chứa email đó sang nơi công khai.

## Promotion: tạo dedicated admin

1. Tạo một email/tài khoản riêng chỉ dành cho admin.
2. Đăng ký tài khoản qua flow ParkSmart/Supabase bình thường.
3. Hoàn tất xác minh email Supabase.
4. Đăng nhập ParkSmart một lần để backend tạo `profiles` row với
   `app_role=user` và parking identity do backend cấp.
5. Đăng xuất hoàn toàn khỏi tài khoản đó.
6. Operator đăng nhập Supabase Dashboard bằng tài khoản quản trị và mở SQL Editor.
7. Thay `<ADMIN_EMAIL>` khi chạy câu lệnh read-only sau. Kết quả phải có **chính
   xác một row** trong `auth.users`, đúng email và `email_confirmed_at` khác null.
8. Trên cùng row, xác minh profile tồn tại và `app_role=user`. Nếu thiếu profile,
   sai role, email chưa confirmed hoặc số row khác 1, dừng và điều tra; không chạy
   promotion SQL.

```sql
SELECT
    u.id AS auth_user_id,
    u.email AS auth_email,
    u.email_confirmed_at,
    p.email AS profile_email,
    p.app_role,
    p.parking_user_id,
    p.default_vehicle_id
FROM auth.users AS u
LEFT JOIN public.profiles AS p ON p.id = u.id
WHERE lower(u.email) = lower('<ADMIN_EMAIL>');
```

9. Chỉ sau khi các kiểm tra trên đạt yêu cầu, chạy toàn bộ transaction dưới đây.
   UUID được resolve từ `auth.users`; operator không nhập UUID thủ công. Update chỉ
   chọn email đã confirmed và profile hiện còn là `user`.
10. Promotion đồng thời xóa liên kết `parking_user_id` và `default_vehicle_id` khỏi
    dedicated admin account.
11. `RETURNING` phải hiển thị đúng một row với `app_role=admin`,
    `parking_user_id=null` và `default_vehicle_id=null`. Guard sẽ làm transaction
    lỗi nếu số row sửa khác 1. Khi có lỗi hoặc kết quả khác mong đợi, chạy
    `ROLLBACK;`, không retry trước khi xác định nguyên nhân.

```sql
BEGIN;

CREATE TEMP TABLE admin_promotion_result ON COMMIT DROP AS
WITH eligible AS (
    SELECT u.id
    FROM auth.users AS u
    JOIN public.profiles AS p ON p.id = u.id
    WHERE lower(u.email) = lower('<ADMIN_EMAIL>')
      AND u.email_confirmed_at IS NOT NULL
      AND p.app_role = 'user'
),
single_eligible AS (
    SELECT id
    FROM eligible
    WHERE (SELECT count(*) FROM eligible) = 1
),
updated AS (
    UPDATE public.profiles AS p
    SET app_role = 'admin',
        parking_user_id = NULL,
        default_vehicle_id = NULL
    FROM single_eligible AS candidate
    WHERE p.id = candidate.id
    RETURNING
        p.id,
        p.email,
        p.app_role,
        p.parking_user_id,
        p.default_vehicle_id
)
SELECT * FROM updated;

DO $$
DECLARE
    modified_count integer;
BEGIN
    SELECT count(*) INTO modified_count FROM admin_promotion_result;
    IF modified_count <> 1 THEN
        RAISE EXCEPTION
            'Admin promotion aborted: expected 1 updated row, got %',
            modified_count;
    END IF;
END
$$;

TABLE admin_promotion_result;
COMMIT;
```

Nếu transaction đang ở trạng thái lỗi hoặc `TABLE admin_promotion_result` không
trả đúng một row, chạy:

```sql
ROLLBACK;
```

12. Đăng nhập lại bằng dedicated admin trong một browser profile riêng, không dùng
    tab/session của user thường.
13. Gọi `GET /api/v1/auth/me` và xác minh `role=admin`,
    `parking_user_id=null`, `default_vehicle_id=null`.
14. Xác minh một admin API, ví dụ `GET /api/v1/admin/events`, thành công.
15. Trong browser/profile khác, xác minh tài khoản user thường gọi cùng admin API
    nhận `403 ADMIN_REQUIRED`; request anonymous phải nhận `401 AUTH_REQUIRED`.

Ghi lại thời gian, operator, email admin, hành động, số row thay đổi và kết quả xác
minh trong protected audit record có quyền truy cập giới hạn. Không ghi password,
access token, refresh token, API key, `DATABASE_URL` hoặc service-role key.

## Emergency revoke

1. Ưu tiên disable/ban dedicated admin account trong Supabase Auth để chặn phát
   hành và sử dụng session mới. Thu hồi session hiện có theo khả năng vận hành của
   Supabase.
2. Xác minh đúng một `auth.users` row theo email, rồi hạ `profiles.app_role` từ
   `admin` xuống `user` bằng một transaction có điều kiện và `RETURNING`, tương tự
   promotion guard. Giữ `parking_user_id` và `default_vehicle_id` là null.
3. Nếu update không sửa đúng một row, `ROLLBACK` và điều tra thay vì mở rộng điều
   kiện update.
4. Xác minh admin API không còn truy cập được.

Sau khi account đã bị disable/ban, operator có thể dùng transaction sau. Nó chỉ
chọn đúng dedicated admin hiện có role `admin`, resolve UUID từ `auth.users` và tự
abort nếu không sửa đúng một row.

```sql
BEGIN;

CREATE TEMP TABLE admin_revoke_result ON COMMIT DROP AS
WITH eligible AS (
    SELECT u.id
    FROM auth.users AS u
    JOIN public.profiles AS p ON p.id = u.id
    WHERE lower(u.email) = lower('<ADMIN_EMAIL>')
      AND p.app_role = 'admin'
),
single_eligible AS (
    SELECT id
    FROM eligible
    WHERE (SELECT count(*) FROM eligible) = 1
),
updated AS (
    UPDATE public.profiles AS p
    SET app_role = 'user',
        parking_user_id = NULL,
        default_vehicle_id = NULL
    FROM single_eligible AS candidate
    WHERE p.id = candidate.id
    RETURNING
        p.id,
        p.email,
        p.app_role,
        p.parking_user_id,
        p.default_vehicle_id
)
SELECT * FROM updated;

DO $$
DECLARE
    modified_count integer;
BEGIN
    SELECT count(*) INTO modified_count FROM admin_revoke_result;
    IF modified_count <> 1 THEN
        RAISE EXCEPTION
            'Admin revoke aborted: expected 1 updated row, got %',
            modified_count;
    END IF;
END
$$;

TABLE admin_revoke_result;
COMMIT;
```

Việc hạ role thành `user` trong khi parking identity là null **không** biến
dedicated admin thành tài khoản user hợp lệ. Giữ tài khoản bị disable/ban; nếu cá
nhân đó cần sử dụng ParkSmart như user, họ phải đăng ký một tài khoản user riêng
qua flow bình thường.

Protected audit record của revoke phải có thời gian, operator, email admin, hành
động, số row thay đổi và kết quả xác minh, đồng thời phải giới hạn quyền truy cập.
Không ghi password, access token, refresh token, API key, `DATABASE_URL` hoặc
service-role key.
