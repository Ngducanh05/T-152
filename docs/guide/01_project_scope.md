# 01 — Project Scope

## 1. Thông tin tài liệu

* Project: ParkSmart AI
* Owner: Leader
* Status: Approved
* Target release: MVP v0.1.0
* Development duration: 2 weeks

## 2. Mục tiêu dự án

ParkSmart AI là hệ thống AI Agent hỗ trợ cư dân, bảo vệ và Ban quản lý trong việc quản lý phương tiện và điều phối chỗ đỗ xe.

MVP cần chứng minh được ba giá trị:

1. Người dùng có thể sử dụng ngôn ngữ tự nhiên để thực hiện nghiệp vụ gửi xe.
2. AI Agent gọi đúng công cụ nghiệp vụ và không tự tạo dữ liệu.
3. Yêu cầu vượt định mức phải có Ban quản lý phê duyệt.

## 3. Đối tượng sử dụng

### Resident

* Quản lý phương tiện của mình.
* Xem khu vực còn chỗ.
* Đặt và hủy vị trí đỗ.
* Đăng ký xe khách.
* Tra cứu trạng thái yêu cầu.
* Hỏi Agent về nội quy và nghiệp vụ.

### Security

* Xem trạng thái bãi xe.
* Xem danh sách xe khách hợp lệ.
* Check-in và check-out xe khách.
* Cập nhật trạng thái vị trí đỗ trong môi trường demo.

### Admin

* Xem và xử lý yêu cầu vượt định mức.
* Quản lý trạng thái bãi xe.
* Xem thông báo và audit log cơ bản.
* Quản lý một số chính sách hệ thống.

## 4. Chức năng bắt buộc của MVP

### Authentication

* Đăng nhập bằng Supabase Auth.
* FastAPI xác minh access token.
* Phân quyền resident, security và admin ở backend.

### Vehicle management

* Xem danh sách phương tiện.
* Đăng ký phương tiện.
* Cập nhật thông tin được phép.
* Ngừng sử dụng phương tiện.
* Kiểm tra biển số trùng.
* Tạo yêu cầu phê duyệt khi vượt định mức.

### Parking management

* Xem tầng và khu vực gửi xe.
* Xem số lượng slot còn trống.
* Xem trạng thái từng slot.
* Đặt chỗ và hủy đặt chỗ.
* Nhận hướng dẫn tầng, khu và mã slot.

### Guest registration

* Cư dân đăng ký xe khách.
* Bảo vệ kiểm tra xe khách còn hiệu lực.
* Bảo vệ check-in và check-out.

### AI Agent

Agent hỗ trợ:

* Kiểm tra chỗ trống.
* Đặt chỗ.
* Hủy đặt chỗ.
* Đăng ký phương tiện.
* Đăng ký xe khách.
* Kiểm tra trạng thái yêu cầu.
* Tra cứu nội quy.

### HITL

Yêu cầu đăng ký xe vượt định mức phải:

1. Tạo phương tiện ở trạng thái pending.
2. Tạo approval request.
3. Chờ admin duyệt hoặc từ chối.
4. Gửi notification cho người yêu cầu.
5. Ghi audit log.

### Realtime

Giao diện cập nhật khi:

* Trạng thái slot thay đổi.
* Reservation thay đổi.
* Approval request được xử lý.
* Có notification mới.

## 5. Giả định MVP

* Chưa có camera hoặc cảm biến thật.
* Trạng thái slot được tạo bởi Slot Simulator.
* Dữ liệu demo không phải dữ liệu người dùng thật.
* Frontend và backend giao tiếp qua REST API.
* Supabase được sử dụng cho Auth và Realtime.
* PostgreSQL là nguồn sự thật của dữ liệu nghiệp vụ.

## 6. Ngoài phạm vi MVP

Không triển khai:

* Nhận diện biển số bằng camera thật.
* Kết nối cảm biến vật lý.
* Điều khiển barrier.
* Thanh toán phí gửi xe.
* Mobile application riêng.
* Dẫn đường 3D.
* Computer vision chống gian lận.
* Machine learning dự báo tải phức tạp.
* Kubernetes.
* Kiến trúc microservice.
* Tích hợp hệ thống doanh nghiệp thật.

## 7. Điều kiện hoàn thành MVP

MVP hoàn thành khi:

* Ba vai trò đăng nhập được.
* Cư dân quản lý phương tiện được.
* Cư dân xem và đặt slot được.
* Không thể đặt một slot cho hai người cùng lúc.
* Cư dân đăng ký xe khách được.
* Bảo vệ xử lý xe khách được.
* Xe vượt định mức tạo approval request.
* Admin duyệt hoặc từ chối được.
* Agent gọi đúng tool.
* Agent không tự bịa trạng thái slot.
* Agent không tự duyệt approval.
* Có audit log cho thao tác quan trọng.
* Có kiểm thử API và Agent.
* Backend và frontend deploy được.
* Luồng demo chính chạy ổn định.

## 8. Quy tắc thay đổi phạm vi

Mọi yêu cầu mới phải được Leader đánh giá.

Một chức năng chỉ được thêm vào MVP khi:

* Không làm ảnh hưởng milestone hiện tại.
* Có người chịu trách nhiệm rõ ràng.
* Có acceptance criteria.
* Có đủ thời gian để code, test và tích hợp.
* Leader cập nhật tài liệu và issue tương ứng.
