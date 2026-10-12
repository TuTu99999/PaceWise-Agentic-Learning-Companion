# Private API và Google Calendar quota — 09/10/2026

## Kết quả triển khai

PaceWise frontend mã hóa request/response JSON, bao gồm tên/email, ID người dùng, môn học, task và nội dung học tập. Trên Network chỉ còn envelope; target REST path/query/body nằm trong ciphertext và browser gọi `/api/v1/private/dispatch`.

**Đây là bảo vệ payload trên đường gọi API, không phải giấu dữ liệu khỏi chủ trình duyệt sau giải mã, không phải mã hóa mọi cột database, không thay thế HTTPS hoặc phân quyền.** Database vẫn giữ ID nội bộ để bảo toàn foreign key/quan hệ LMS. UI, bộ nhớ JavaScript và dữ liệu người dùng chủ động xuất vẫn đọc được bởi chính người dùng. LMS simulator vẫn dùng API riêng, không được chuyển toàn bộ sang protocol này.

## 1. Protocol và boundary

- P-256 ECDH, khóa client tạm mới cho mỗi request; HKDF-SHA256; AES-256-GCM với nonce ngẫu nhiên 96 bit.
- Private key backend lưu bền vững tại `data/private-api-p256.pem`, không nằm trong frontend/Git/Docker image. Public key, salt và nonce là metadata không bí mật.
- Key client không extractable, không lưu localStorage/cookie. Khóa backend là khóa server tĩnh: **không tuyên bố forward secrecy đối với việc khóa server sau này bị lộ**. Production TLS vẫn bắt buộc.
- Request có timestamp; nonce đã dùng được lưu trong database, hết hạn được dọn. Chặn payload sửa tag, quá hạn, replay, recursive dispatch và target ngoài API. Không có fallback âm thầm về plaintext.
- Backend dispatch nội bộ qua ASGI; giữ cookie/CSRF và cùng dependency xác thực/phân quyền của REST gốc. Không tin user/role header do client đưa vào. Biết ID hoặc có public key không tạo quyền đọc resource.
- `PRIVATE_API_REQUIRED=true` chặn endpoint JSON cũ bằng 426. Exceptions là public config, encrypted gateway/file references, OAuth callback và SSE. OAuth callback vẫn cần state/PKCE/session; SSE chỉ gửi tín hiệu invalidation không chứa course/event ID.
- Các link download PDF nội bộ trong JSON được thay bằng reference mã hóa, có hạn và ràng buộc session. File proxy vẫn kiểm tra quyền file hiện tại qua endpoint gốc; không có bearer link công khai. File mở cho người đã có quyền vẫn là PDF đọc được, không phải file mã hóa không xem được.
- Binary export ICS đi qua encrypted envelope rồi frontend giải mã để tải. Upload học liệu hiện ở LMS; gateway không nhận FormData upload legacy PaceWise.
- Browser cần Web Crypto trong **HTTPS hoặc localhost**. Demo qua IP LAN dùng HTTP không có `crypto.subtle` sẽ bị chặn; phải cấu hình HTTPS, không mở fallback để “cho chạy”.

Không thể đảm bảo DevTools/debugger của chính người dùng không xem được dữ liệu sau giải mã. Không phải kiểm toán/pentest độc lập hoặc cam kết “bảo mật hết”.

## 2. Google Calendar: bảo vệ quota dùng chung

| Cấu hình | Giá trị local |
|---|---:|
| `GOOGLE_API_PROJECT_PER_MINUTE` | 1500 |
| `GOOGLE_API_USER_PER_MINUTE` | 60 |
| `GOOGLE_API_DAILY_BUDGET` | 50000 |
| `GOOGLE_API_MAX_CONCURRENT` | 16 |
| `GOOGLE_API_CACHE_SECONDS` | 300 |

- Limiter lưu database chung, dùng transaction và row lock PostgreSQL; SQLite dùng write transaction trong test. Không phải bộ đếm RAM riêng mỗi backend. Tất cả replica phải dùng cùng database và namespace/quy tắc.
- Tính quota **từng outbound HTTP attempt**, kể cả refresh token, userinfo, call lỗi, retry, revoke. Cache hit không gọi Google nên không bị tính như một outbound attempt.
- Cộng bucket phút hiện tại và phút trước để không burst qua ranh giới phút; cộng bucket giờ trong khoảng hiện tại + 24 giờ trước để giới hạn ngày theo cửa sổ bảo thủ. Throughput thực có thể thấp hơn số cấu hình; không dùng “reset lúc 00:00” để tăng quota.
- Tối đa 16 outbound call đang chạy; lease hết hạn và được trả trong `finally`. Lỗi shared store **fail closed**, không bỏ qua limiter.
- Mỗi tài khoản chỉ có một thao tác Google đang chạy; spam sync/export song song trả 429 + `Retry-After`.
- Cache freebusy theo user, grant và khoảng ngày/time zone. Cache account email và access token có TTL; nội dung cache mã hóa Fernet, không lưu access token dạng rõ. Grant thay đổi không dùng lại cache cũ. Freebusy có thể trễ tối đa TTL; không gọi là realtime tuyệt đối.
- Rate-limit Google 403/429 tạo cooldown dùng chung. Retry có jitter, tối đa một lần retry, chỉ khi delay ngắn; mọi retry phải xin quota lại. Không có retry vô hạn.
- Export dùng event ID opaque ổn định HMAC theo user/calendar/block; khi gặp 409 đọc lại event đó. Block đã xuất hết được bỏ qua trước khi refresh token. Không ghi block ID gốc trong Google private extended property cho các event mới.
- Nếu bị giới hạn sau khi xuất một phần: links đã commit vẫn giữ; gửi lại sẽ bỏ qua block đã xuất. Ngắt kết nối chỉ xóa local cache/link, không xóa event Google; nối lại cùng account có thể phục hồi event qua ID ổn định.
- Telemetry: `pacewise_google_admission_total` theo outcome, không gắn user ID/email vào labels.

**Ngân sách này chỉ bảo vệ các request chạy qua PaceWise.** App khác cùng Google project, thay đổi quota/tính phí, rotation secret dùng tạo event ID hoặc admin thay cấu hình không nằm trong bảo đảm này. Phải đối chiếu quota thật trong Cloud Console và đặt giới hạn thấp hơn, dành phần dự phòng cho app khác.

Google cập nhật quota trong năm 2026; tài liệu công bố ngưỡng ngày trước phí và thông báo thay đổi. Không thể chốt “API luôn miễn phí” hoặc suy ra cứ vượt tốc độ là lập tức bị tính tiền. Xem [usage limits/pricing chính thức](https://developers.google.com/workspace/calendar/api/guides/quota). Event ID do client đặt tuân thủ định dạng của [Events.insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert).

## 3. Test/evidence

Các test kỹ thuật kiểm tra:

1. Login, đọc hồ sơ và logout qua ciphertext; response không chứa tên/email/ID field rõ.
2. Plain API bị chặn; encrypted request không vượt qua CSRF hoặc quyền course.
3. Chặn tamper, replay, expired timestamp, external URL và recursive dispatch.
4. Link PDF mở trong phiên đúng; phiên tài khoản khác trả 403.
5. Web Crypto client decrypt được response; giữ `Retry-After`; không fallback khi server trả plaintext 200.
6. Shared limiter qua ranh giới phút/ngày, giới hạn mỗi user/global và fail-closed khi DB lỗi.
7. Cache status/freebusy tránh gọi Google lặp; cache không chứa nội dung rõ.
8. Stable event ID phục hồi 409, không tạo request ID mới cho cùng block.
9. 1.000 request tổng từ 32 worker với fake outbound provider: lần targeted **27 accepted / 973 limited / peak=2**, cấu hình cap=4 và budget=40. Số accepted/peak phụ thuộc lịch chạy máy; invariant là peak≤4, accepted≤40, budget chính xác và leases trả hết.

**Test 1.000 request này không gọi Google thật**, không chứng minh 1.000 sinh viên được phục vụ đồng thời hoặc đảm bảo latency production. Hệ thống chủ động từ chối phần vượt giới hạn để bảo vệ quota.

Reports: [backend full](../evals/reports/private-calendar-backend-2026-10-09.xml), [targeted](../evals/reports/private-calendar-targeted-2026-10-09.xml), [frontend](../evals/reports/private-calendar-frontend-2026-10-09.xml).

Backend full: **547 passed**; thêm timeout toàn HTTP call được kiểm tra lại bằng **33 Google tests passed**. Frontend sau sửa Origin: **208 passed / 52 files**, production build/typecheck pass, main chunk **351.13 kB / gzip 111.48 kB**.

HTTP thật local Docker/PostgreSQL: cả student/instructor login 200 → sang LMS 303 → về PW 200 → logout 200 → cookie cũ/LMS liên kết 401. Plain `/auth/me` trả 426, không có hồ sơ. Smoke runner: `scripts/evaluate_auth_bridge.py`, đã cập nhật encrypted client.

**Giới hạn smoke cũ:** script tự đặt Origin nên không phát hiện lỗi trình duyệt gửi `Origin: null` khi form POST gặp `Referrer-Policy: no-referrer`. Bản sửa dùng `fetch(mode: cors, credentials: include)` nhận JSON 200 rồi mới điều hướng LMS; giữ no-referrer và không đưa ticket vào URL. LMS chỉ cho CORS từ origin cấu hình bằng `PACEWISE_URL`, vẫn chặn origin thiếu/null/sai và ticket replay. Native form cũ còn trả 303 để tương thích.

Regression Origin: **74 simulator tests passed**, gồm hai role, JSON/cookie/CORS, preflight, origin xấu và replay; **4 bridge frontend tests passed** trong bộ 208 test. Evidence: [simulator](../evals/reports/lms-origin-regression-2026-10-09.xml), [frontend](../evals/reports/frontend-origin-regression-2026-10-09.xml). [MDN Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin) mô tả trường hợp form POST bị null do referrer policy; CORS fetch không thuộc trường hợp này.

Tại thời điểm kiểm tra bản sửa, Docker Linux daemon không hoạt động (`dockerDesktopLinuxEngine` không tồn tại). **Chưa áp dụng/retest runtime bản CORS mới**, không coi unit/HTTP fixture tests là kiểm chứng trình duyệt thật. Smoke runner đã chuyển sang JSON acknowledgement để dùng sau rebuild.

Cập nhật sau đó ngày 09/10: Docker đã hoạt động lại; backend, worker, frontend và LMS simulator được rebuild. HTTP encrypted/CORS hai role đã pass với bridge 200, ticket replay và các phiên sau logout đều 401. Full regression hiện tại: backend **560**, frontend **217** pass; bộ Google pool/cache/export **38** pass. Xem [Tổng quan giảng viên và Calendar](teacher-overview-calendar-evaluation-2026-10-09.md) cho số liệu, test pool một connection và giới hạn chưa benchmark 1.000 user.

Chưa có pentest độc lập, full-stack 1.000 concurrent thật, thao tác Google thật trên 1.000 account hoặc xác nhận Google billing settings của project. Không chạy tải bằng credential thật vì có thể tiêu quota/tạo lịch người dùng.

## 4. Vận hành

`.env` local đã bật `PRIVATE_API_REQUIRED=true` và các giới hạn ở trên, không sửa Google credentials. Mọi backend replica phải mount cùng private key bền vững; không tạo riêng key giữa các replica. Giữ secret ký session ổn định để giữ event ID/counter user identity ổn định.

```powershell
docker compose up -d --build backend worker frontend lms-simulator
```

Sau update frontend: **Ctrl+F5**, đăng nhập lại và xem `/private/dispatch` trong Network. Đừng gửi ciphertext/keys/cookies lên chat để kiểm tra. Khi rotate private key phải reload frontend để lấy public key mới. HTTPS, bảo vệ file secret/backup, giới hạn ingress/body size và network riêng database vẫn phải làm khi deploy.

SSO yêu cầu URL frontend thực tế có cùng scheme/host/port với `PACEWISE_URL`; `localhost` và `127.0.0.1` là hai origin khác nhau. Local mặc định: mở `http://localhost:5173`, LMS `http://localhost:8010`. Sau rebuild chạy `.\.venv\Scripts\python.exe scripts/evaluate_auth_bridge.py` để kiểm tra cả hai role qua HTTP; script không in credential/ticket/cookie.
