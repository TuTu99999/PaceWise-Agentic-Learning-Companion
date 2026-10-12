# Google Calendar — audit role sinh viên

Ngày: 2026-10-09. Phạm vi: đọc code, test với provider giả lập và kiểm tra cấu hình local. **Không đăng nhập Google, không tạo/xóa sự kiện Google, không thay code Calendar trong đợt này.**

## Kết luận

**Đã có nền tảng tích hợp, chưa thể chốt production-ready và không phải chỉ cần Gmail edu thật.** Repo không bắt buộc địa chỉ `.edu`: tài khoản Google có thể khác tài khoản trường. Test kết nối dùng `personal.calendar@gmail.com` dù phiên PaceWise là `student@example.edu`.

Cấu hình backend local được kiểm tra bằng `Settings()` hiện trả:

```json
{
  "configured": false,
  "client_id_present": false,
  "client_secret_present": false,
  "token_encryption_key_present": false,
  "redirect_uri": "http://localhost:8000/api/v1/integrations/google-calendar/callback",
  "return_url": "http://localhost:5173/#/settings"
}
```

Chỉ in trạng thái có/không và URL, không in secrets. Đây là cấu hình source local tại thời điểm audit, không phải kiểm tra env của container production.

## Luồng đã có

```text
Sinh viên → Settings → Kết nối Google Calendar
→ backend tạo state + PKCE
→ Google hỏi quyền
→ callback kiểm tra state và đổi code lấy token
→ mã hóa refresh token ở backend
→ đọc primary calendar free/busy theo yêu cầu
→ nhập lịch bận vào ràng buộc Plan
→ sinh viên xác nhận rồi mới xuất study block
```

Có quyền role student, CSRF cho hành động thay đổi, state có hạn dùng, PKCE S256, mã hóa refresh token, kiểm tra timezone/window, xác nhận trước export và revoke trước ngắt kết nối. Không có kiểm tra bắt buộc `.edu`.

## Test thực tế

```powershell
$env:DATABASE_URL='sqlite:///./tmp/calendar-audit-test-20261009.db'
.\.venv\Scripts\python.exe -m pytest tests/test_api/test_google_calendar.py tests/test_services/test_google_calendar_client.py -q
```

Output: **18 passed in 1,09s**. [JUnit](../evals/reports/google-calendar-audit-2026-10-09.xml).

Coverage đã có: scopes/state/PKCE, callback mã hóa token và từ chối dùng lại state tuần tự, freebusy/CSRF, xác nhận export, chống duplicate tuần tự cùng block ID, revoke, Google account khác tài khoản trường, teacher 403, timezone/window sai và lỗi provider.

Test đang mock HTTP Google; **không chứng minh consent, chính sách tổ chức, token refresh hay quota với tài khoản thật**. Chưa có test browser OAuth end-to-end hoặc test concurrent export/callback trên PostgreSQL.

## Vấn đề còn tồn tại

| Vấn đề | Bằng chứng code / output | Ảnh hưởng và hướng xử lý |
| --- | --- | --- |
| Status còn `connected=true` khi refresh/provider lỗi | `src/api/google_calendar.py:status` dựa vào connection row; exception chỉ làm `accountEmail=null` | UI dễ báo kết nối tốt dù token cần cấp quyền lại. Phân biệt connected/degraded/reauth_required; không gán mọi lỗi mạng thành token invalid |
| Export block đổi giờ vẫn bị skip | `export_events` chỉ tìm link bằng user/block ID, không đối chiếu start/end | Chưa phải sync cập nhật lịch. Cần upsert/diff có xác nhận; chỉ update event đã xác minh do PaceWise tạo |
| Link cũ còn sau disconnect/reconnect | `disconnect` chỉ xóa connection, EventLink không được dọn/bind Google subject | Đổi tài khoản Google có thể vẫn bị skip. Link phải scope theo Google account + calendar + block; không tự xóa sự kiện remote khi chưa được đồng ý |
| Busy cũ còn sau ngắt kết nối | `SettingsPage.disconnectCalendar` không dispatch bỏ các slot `google-*` | Planner vẫn dùng busy đã nhập. Cần định nghĩa giữ snapshot/offline hay xóa, hiển thị tuổi dữ liệu rõ ràng |
| “7 ngày tới” dùng tuần plan | `SettingsPage.importBusyTime` dùng `weekStart` của plan | Label và window có thể không khớp realtime; nhập lại xóa mọi slot `google-*`, kể cả ngoài window. Cần ghi rõ tuần đang đồng bộ và merge theo date/window |
| Busy qua nửa đêm hụt một phút | `_busy_slots` chốt ngày ở `23:59`, ngày sau bắt đầu `00:00` | Khoảng `[23:59,24:00)` không bị khóa. Tái hiện busy 22:00–02:00 cho output bên dưới; cần biểu diễn boundary cuối ngày đúng |
| Google response thiếu calendar bị coi là rảnh | client `freebusy` dùng `calendar or {}` | Fail-open gây xếp lịch sai. Thiếu calendar cần lỗi rõ ràng, không thay snapshot bằng lịch trống |
| Export đồng thời có thể tạo event thừa | Tạo Google event trước rồi mới commit unique local link | Local dedup không ngăn side effect remote. Cần idempotency phía Google hoặc lock/outbox/reconciliation; chưa tái hiện concurrent trên provider thật |
| Consume OAuth state chưa atomic | Callback đọc state rồi set used; không conditional update/row lock | Có rủi ro race; test replay tuần tự chưa đủ. Cần consume atomic transaction và test concurrent |

Output tái hiện bằng helper local, không gọi Google:

```json
[
  {"date":"2026-10-09","start":"22:00","end":"23:59"},
  {"date":"2026-10-10","start":"00:00","end":"02:00"}
]
```

Tài liệu/metadata busy hiện chỉ nhận một `calendar_id` (mặc định `primary`); không tự đọc tất cả calendar của tài khoản, không webhook/realtime hai chiều. Không nên quảng bá thành full calendar sync.

## Cấu hình tối thiểu để thử OAuth thật

1. Tạo Google Cloud project, bật Calendar API.
2. Cấu hình OAuth consent/audience; nếu thử nghiệm, cho tài khoản demo vào danh sách được phép thử.
3. Tạo OAuth client loại **Web application**; đăng ký redirect URI đúng tuyệt đối với backend public callback.
4. Đặt client ID, secret và khóa Fernet ở backend; frontend không được giữ các secret này. Theo [hướng dẫn OAuth web server của Google](https://developers.google.com/identity/protocols/oauth2/web-server).

Ví dụ env local, chỉ là placeholder, chưa được áp dụng:

```dotenv
GOOGLE_CLIENT_ID=<web-client-id>
GOOGLE_CLIENT_SECRET=<backend-secret>
GOOGLE_TOKEN_ENCRYPTION_KEY=<fernet-key>
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/integrations/google-calendar/callback
GOOGLE_OAUTH_SUCCESS_URL=http://localhost:5173/app#/settings
```

Có thể dùng `GOOGLE_CLIENT_SECRET_FILE` và `GOOGLE_TOKEN_ENCRYPTION_KEY_FILE` cho secrets mount. Khóa Fernet cần giữ ổn định sau restart để giải mã token đã lưu; không commit key vào repo.

Production: callback dùng HTTPS domain public, không dùng localhost; return URL phải về đúng route Settings của frontend đang deploy. Kiểm tra env thực tế trong container sau cấu hình/rebuild.

Scopes repo hiện yêu cầu `openid email`, `calendar.freebusy`, `calendar.events.owned`. Scope `events.owned` cho phép truy cập sự kiện trên calendar sở hữu, **không tự giới hạn quyền Google chỉ vào event do PaceWise tạo**. Code upsert/xóa tương lai phải tự xác minh marker/account/calendar và xin xác nhận. Rà least-privilege và quy trình verification theo [Calendar scopes của Google](https://developers.google.com/workspace/calendar/api/auth).

## Checklist nghiệm thu thật, chưa chạy

- Consent bằng một tài khoản Google được phép; callback quay lại đúng phiên PaceWise.
- Từ chối consent/thiếu scope không tạo connection giả.
- Access token hết hạn được refresh; refresh bị revoke hiện yêu cầu kết nối lại.
- Freebusy timezone Việt Nam và qua nửa đêm; không import dữ liệu sai window.
- Export một block với xác nhận, kiểm tra giờ/title trên Google.
- Đổi giờ block và export lại: chỉ cập nhật một event đúng tài khoản, không duplicate.
- Ngắt/reconnect cùng và khác Google account: không dùng link/busy cũ nhầm scope.
- Mô phỏng lỗi Google và thao tác đồng thời; không mất dữ liệu bận hoặc tạo event remote mồ côi.

**Khuyến nghị:** cấu hình OAuth đủ để thử kết nối cơ bản bằng tài khoản demo được phép, nhưng nên sửa các điểm status, upsert, account-scoped links và busy lifecycle trước khi chốt production. Audit này không tự triển khai các sửa đổi Calendar.
