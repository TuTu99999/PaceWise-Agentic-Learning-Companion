# Settings và Google Calendar — sửa lỗi / kiểm chứng

Ngày: 2026-10-09. Phạm vi: bỏ hai khối thông tin trong Settings, sửa OAuth quay về ứng dụng và kiểm tra scope.

## Thay đổi

- Bỏ card **Thời gian rảnh mặc định** và **Quyền riêng tư** khỏi Settings sinh viên. Không xóa availability đã lưu, không thay quyền truy cập giảng viên hay chính sách dữ liệu. Availability vẫn dùng trong trình tạo Plan.
- Đổi `GOOGLE_OAUTH_SUCCESS_URL` thành `http://localhost:5173/app#/settings` trong cấu hình local, default, env example và Docker Compose. `/` là landing page; `/app` mới là ứng dụng HashRouter. Google redirect URI của backend không đổi.
- Chuẩn hóa hai alias identity đã biết: `email`/`userinfo.email`, `profile`/`userinfo.profile`. Không nới lỏng Calendar scopes; đối chiếu grant trả về từ token endpoint, không tin scope ở query của trình duyệt.
- Token response không báo scope thì không mặc định coi đã cấp toàn bộ quyền được yêu cầu.

Google mô tả scope được cấp có thể dùng tên tương đương khác scope yêu cầu: [OAuth 2.0 — granted scopes](https://developers.google.com/identity/protocols/oauth2). Đây là nguyên nhân tái hiện bằng fixture canonical email; chưa ghi token response của lần consent thật để đối chiếu và không đưa token/secrets vào log.

## Test và output thực tế

| Case | Kết quả |
| --- | --- |
| Settings không còn hai card; tài khoản, Calendar, ICS, trạng thái đồng bộ còn nguyên | Pass; không dispatch đổi availability khi mở trang |
| Google trả literal `email` hoặc canonical `userinfo.email` cùng đủ Calendar scopes | Pass; token được mã hóa và redirect về `/app#/settings?google_calendar=connected` |
| Thiếu email, thiếu freebusy, thiếu events, scope không hợp lệ hoặc trống | Pass; callback trả error, không lưu connection |
| Browser query khai đủ scope nhưng token grant thiếu quyền | Pass; không dùng query để vượt kiểm tra quyền |
| Token endpoint bỏ scope, trả null hoặc rỗng | Pass; không suy diễn đã cấp quyền |
| Từ chối consent / không có refresh token | Pass; quay về `/app`, không landing page |
| Replay state | Pass; lần thứ hai HTTP 400 |
| Xử lý callback trên frontend connected/denied/error | Pass; dọn query kết quả, giữ pathname `/app` |
| Tài khoản Google khác email LMS | Pass; hiển thị email Google từ status API |
| Export study blocks | Pass; phải xác nhận ở dialog trước khi gọi API ghi Google |

Output:

```text
Calendar targeted: 28 passed
Settings targeted: 6 passed
Backend regression: 483 passed
Frontend regression: 42 files, 174 passed
TypeScript + Vite production build: passed
Ruff (Calendar source + tests): All checks passed
```

Bằng chứng: [Calendar JUnit](../evals/reports/google-calendar-oauth-fixes-2026-10-09.xml), [backend JUnit](../evals/reports/settings-calendar-backend-2026-10-09.xml), [frontend JUnit](../evals/reports/settings-calendar-frontend-2026-10-09.xml).

Backend tests dùng database SQLite riêng; Google HTTP được mock. Không tạo/xóa sự kiện trên tài khoản Google thật khi chạy test. Test frontend là component tests, chưa phải browser OAuth end-to-end.

## Phần còn cần nghiệm thu thật

Đã build/recreate riêng hai container backend/frontend, không xóa volumes/database. Backend/frontend healthy; `/health`, `/app` và Settings JS asset trả HTTP 200. Backend đang chạy báo `configured=true`, return URL `/app#/settings`, alias email được hỗ trợ. Không in secrets khi kiểm tra.

Người dùng mở `/app#/settings`, bấm kết nối lại, chọn Google Test user và cấp quyền. Xác nhận quay về Settings, hiện email đúng; tiếp đó thử đọc lịch bận. Không tái sử dụng code/state của lần callback đã thất bại.

Các vấn đề Calendar ngoài phạm vi lần sửa này (status degraded, cập nhật event khi đổi giờ, lifecycle busy/link cũ, concurrency) vẫn được ghi ở [audit Calendar](google-calendar-readiness-audit.md). Không tuyên bố toàn bộ tích hợp production-ready hoặc consent thật đã pass chỉ từ test mock.

## Đề xuất tiện ích Settings — chưa triển khai

1. Cấu hình nhắc deadline, bắt đầu Do, hoàn thành Reflect; bật/tắt từng loại và giờ không làm phiền.
2. Tùy chọn nhịp học: thời lượng phiên, nghỉ giữa phiên; là preference mềm, không thay deadline hay lịch LMS.
3. Trung tâm kết nối: trạng thái Canvas/Google, lần đồng bộ gần nhất, lỗi cần xử lý và nút thử lại; tái dùng luồng sync hiện có, không tạo thêm bộ quản lý học liệu.

Ưu tiên nhắc học vì trực tiếp hỗ trợ chu trình Plan–Do–Reflect. Không thêm tiện ích mới trong lần sửa này khi người dùng mới hỏi ý kiến.
