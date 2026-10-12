# Student reminders & integrations — 2026-10-09

## Phạm vi đã triển khai

Scope vẫn là **Plan → Do → Reflect**. Không thêm LMS CRUD, không ghi điểm, không tự thay deadline và không thêm phase nghiệp vụ mới.

| Chức năng | Hành vi |
|---|---|
| Google Calendar | Chỉ xuất sau student confirm. Sự kiện mới gửi `reminders.useDefault=false`, một override `popup`, `minutes=15`. |
| Nhắc trong ứng dụng | Icon chuông giữ các nhắc đang hiệu lực/sắp đến; không bị giới hạn 3 mục. |
| Thông báo foreground | Phải cấp quyền; claim tại backend trước khi hiển thị để chống gửi trùng giữa các component/tab. |
| Background Web Push | User opt-in → subscription có VAPID → backend lưu job → worker gửi → service worker hiển thị khi tab đóng. Không cần LLM để tạo nhắc. |
| Nhắc deadline | Các mốc hiện có 72 giờ (chưa bắt đầu/thiếu capacity), 24 giờ, 2 giờ. Bỏ bài đã hoàn thành/nộp theo snapshot LMS. |
| Nhắc Do | Mặc định trước 15 phút, chọn lại trong Settings. Chỉ từ block đã xác nhận; không từ draft/provisional. |
| Nhắc Reflect | Sau khi hoàn thành Do 5 phút nếu chưa lưu phản tư. Nhắc hết hiệu lực sau 24 giờ; link mở đúng activity. Không phải delayed assessment. |
| Giờ yên lặng | Asia/Ho_Chi_Minh, hỗ trợ khoảng qua nửa đêm, không nhận hai đầu giờ giống nhau. Không làm mất nhắc trong icon chuông. |
| Giới hạn | 1–3 thông báo chủ động mỗi ngày, chung backend cho foreground/background theo tài khoản. Một nhắc được gửi tới nhiều thiết bị chỉ tính một lần logic. |
| Nhịp học | Session 20–120 phút, nghỉ 5–30 phút; UI chọn các mốc phổ biến, default 90/10. Chỉ ảnh hưởng draft mới. |
| Canvas/Google | Lần sync gần nhất, trạng thái lỗi/stale/degraded, retry. Lỗi mạng không bị gọi nhầm là OAuth chưa cấu hình. |

Google gửi nhắc độc lập với PaceWise. Giới hạn 3/ngày và giờ yên lặng PaceWise **không chỉnh thông báo Google hoặc cài đặt thiết bị**. Hai bên có thể cùng nhắc một ca học.

## Luồng và bảo vệ

```text
Confirmed plan + sessions + reflections + LMS snapshot + preferences
    → workspace persistence (validate + optimistic version)
    → reconcile deterministic reminder jobs
    → independent notification worker (every 30 seconds)
    → permission/quiet hours/daily budget checks
    → encrypted Web Push
    → service worker notification
    → /app#/study/... or /app#/reflect?activity=...
```

- Worker thông báo chạy độc lập với polling LMS: LMS chậm không khiến vòng gửi push phải chờ.
- Endpoint chỉ cho student có session; mutations có CSRF. Subscription không được chuyển cho tài khoản khác; logout xóa đăng ký của session hiện tại.
- Chỉ hỗ trợ endpoint push HTTPS của Chrome/Firefox/Apple/Windows. Không gửi request tới URL tùy ý do client nhập; encryption keys được kiểm tra.
- Tối đa 5 thiết bị/tài khoản. GET status chỉ trả public VAPID key và trạng thái, không trả private key/subscription endpoint.
- Push payload là thông báo chung, không gửi nội dung chatbot, câu trả lời, nhận định Assessment hoặc nội dung Reflect tới lock screen/provider.
- Private VAPID key được xuất bản atomically và giữ ổn định. Production không tự sinh key mới khi thiếu mount.
- API claim và worker dùng receipt/job cùng daily budget; PostgreSQL dùng row lock. Không tăng budget khi mọi lần gửi đều lỗi.
- Delivery failure retry tối đa 3 lần; HTTP 404/410 xóa subscription hết hiệu lực; thông báo lỗi lưu dạng generic.
- Quiet/capped jobs được dời lần thử đến cuối khoảng yên lặng/ngày mới; kiểm tra expiry trước khi gửi. Tài khoản chưa bật push/không có subscription không chiếm batch.
- Job chuyển/xóa theo workspace mới, receipt giữ chống replay. Job hết hạn quá 30 ngày và budget quá 35 ngày được dọn bởi worker.
- Service worker không có fetch/cache handler: không cache dữ liệu học tập hoặc callback OAuth. Click không được chuyển sang domain ngoài.
- Cấu hình nhắc là cấp tài khoản; đăng ký push là từng thiết bị. Không xin quyền khi load trang.

## Test và output thực tế

Chạy trên SQLite **riêng**, không dùng demo database:

```powershell
$env:DATABASE_URL='sqlite:///./tmp/reminder-features-full-v3-20261009.db'
.\.venv\Scripts\python.exe -m pytest tests -q --junitxml=evals/reports/reminder-features-backend-2026-10-09.xml
```

Output thực tế lần chạy cuối: **520 passed in 17.61s**.

Frontend:

```powershell
cd frontend\pacewise
npm.cmd test -- --run --reporter=default --reporter=junit --outputFile=../../evals/reports/reminder-features-frontend-2026-10-09.xml
npm.cmd run build
```

Output thực tế: **48 files, 196 tests passed**. TypeScript + Vite production build pass; main JS chunk khoảng **345.70 kB**, không có cảnh báo chunk >500 kB.

| Case | Kiểm tra | Output quan sát trong test |
|---|---|---|
| R01 | Google event body ở HTTP mock | `useDefault=false`, override duy nhất `popup/15`; export không confirm bị chặn. |
| R02 | Reflect sau Do và đã lưu | Job ở `completedAt + 5 minutes`; saved activity không tạo lại job, study-start không nhắc phiên đã hoàn thành. |
| R03 | Quiet 22:00–07:00 | 22:00/06:59 bị chặn; 07:00/10:00 được phép; 25:00 và hai đầu giống nhau bị reject. |
| R04 | Five due jobs, cap=3, replay | Lần đầu gửi 3; lần sau 0; budget=3. Budget foreground đã dùng 2 thì push chỉ gửi thêm 1. |
| R05 | Permission và click opt-in | Không xin quyền lúc render; enable thành công mới bật preference; lỗi không giả báo enabled. |
| R06 | Library encryption/VAPID thật, transport mock | Body không chứa plaintext `PaceWise`; decrypt AES128GCM ra payload ban đầu; Authorization có VAPID signature. Không gọi provider ngoài. |
| R07 | Provider trả 410 | Xóa subscription, attempts=1, budget=0; không lưu response nhạy cảm. |
| R08 | Nhịp 25/5, LMS bận 08:00–09:00, deadline 12:00 | Block đầu 09:00–09:25, block tiếp 09:30; tất cả trước 12:00; đổi preference không tự áp dụng plan. |
| R09 | URL nội bộ/HTTP/domain giả/provider port khác | Reject subscription; không gọi URL đó. |
| R10 | Backend từ chối foreground duplicate | Không show notification, không dispatch receipt rỗng, không tạo vòng rerender/claim liên tục. |
| R11 | Bài LMS done nhưng progress local cũ | Không tạo deadline/study reminder cho bài đó. |
| R12 | LMS worker đang treo | Vòng push vẫn chạy và gọi sender; lifecycle cancellation kết thúc sạch. |
| R13 | Nhiều worker cùng tạo VAPID key | Các lời gọi nhận cùng một key hoàn chỉnh, không có file tạm sót lại. |

Raw reports:

- [Backend regression](../evals/reports/reminder-features-backend-2026-10-09.xml)
- [Frontend regression](../evals/reports/reminder-features-frontend-2026-10-09.xml)
- [Targeted backend](../evals/reports/reminder-features-targeted-2026-10-09.xml)
- [PostgreSQL runtime smoke](../evals/reports/reminder-features-postgres-2026-10-09.json)

### Docker/PostgreSQL smoke

Backend/frontend healthy, worker running sau rebuild. `/health` trả `ok`, `/app` trả 200; `/pacewise-sw.js` trả 200, `application/javascript`, `Cache-Control: no-store`. VAPID private key được giữ trong data volume, public key dài 87 ký tự; không in secret.

Chạy script [evaluate_reminder_delivery.py](../scripts/evaluate_reminder_delivery.py) bên trong backend container, dùng schema mới ở transaction rồi rollback; sender là mock. Không gửi push thật hoặc sửa dữ liệu sinh viên:

```powershell
$evaluationScript = Get-Content -Raw -Encoding utf8 scripts/evaluate_reminder_delivery.py
$evaluationScript | docker compose exec -T backend python -
```

Output thực tế:

```json
{"database":"postgresql","delivered":3,"replay":0,"daily_budget":3,"provider":"mocked","isolation":"transaction_schema_rolled_back","status":"passed"}
```

Smoke test tìm ra và đã sửa lỗi khác biệt PostgreSQL/SQLite: `substr(id, -10)` không có cùng nghĩa trên PostgreSQL, có thể xóa nhầm daily budget. Đã thay bằng offset dương `length(id)-9`, kiểm tra budget còn giữ sau nhiều vòng gửi. Đây là kiểm chứng đường SQL/delivery, không phải load test concurrent nhiều worker.

## Chạy local và kiểm chứng thiết bị thật

```powershell
docker compose up -d --no-deps --build backend worker frontend
```

1. Vào `http://localhost:5173/app#/settings`, role student.
2. Chọn các loại nhắc, giờ yên lặng và nhịp học. Đợi trạng thái workspace **Đã lưu an toàn**; reload kiểm tra preference vẫn giữ.
3. Bấm **Bật nhắc khi đóng tab**, cho phép notification. Kiểm tra Settings báo thiết bị đã đăng ký.
4. Xác nhận một plan có ca học sắp tới, đợi workspace lưu rồi đóng tab. Backend và worker phải vẫn chạy. Kiểm tra thông báo hệ điều hành và click về đúng ca.
5. Hoàn thành Do, chưa lưu Reflect; sau 5 phút kiểm tra nhắc. Lưu Reflect phải bỏ nhắc đang chờ.
6. Kết nối Google và xác nhận export một block **chưa xuất trước đây**; mở event trên Google kiểm tra popup 15 phút.

Không bật quyền thay người dùng, không tạo event trên Google thật hoặc gửi push thật trong automated tests. Các thao tác thiết bị/OAuth này cần người dùng tự cấp quyền và kiểm tra.

## Giới hạn và đánh giá

- **Engineering regression passed**, chưa đồng nghĩa đã chứng minh OS/browser hoặc Google gửi thông báo thực tế cho tài khoản người dùng. Test provider là mock; test crypto dùng library thật.
- Push khi đóng tab cần browser/OS hỗ trợ, mạng, background delivery được phép. Không cam kết nhận khi tắt máy, force-stop browser hoặc thiết bị chặn thông báo. HTTPS bắt buộc khi không phải localhost; truy cập HTTP qua IP LAN trên điện thoại không đủ.
- Nhắc nền dựa trên workspace/LMS snapshot **đã lưu**, horizon 15 ngày, tối đa 256 candidate jobs/lần reconcile. Thay đổi LMS xảy ra sau khi đóng app chưa tự tái tạo snapshot thông báo cho từng sinh viên. Khi mở app/sync lại, jobs được reconcile. Không gọi đây là đồng bộ deadline realtime toàn diện khi đóng web.
- Thông báo là best-effort. Stable tag + server receipts giảm trùng, nhưng không bảo đảm exactly-once nếu provider đã nhận rồi kết nối bị ngắt trước ACK hoặc worker chết trước commit.
- Không load-test hàng nghìn người dùng/multi-worker contention. PostgreSQL row locks có trong implementation; SQLite tests không chứng minh hành vi concurrent production.
- Sự kiện Google **đã xuất trước bản sửa này** vẫn bị skip, không backfill reminder và không tự cập nhật giờ khi block đổi. Không âm thầm ghi đè lịch cũ; cần thêm flow preview/update có kiểm tra event ownership nếu muốn hỗ trợ sau.
- Giờ yên lặng không thay Google reminders, và cap không giới hạn số nhắc hiển thị trong icon chuông.

## Đề xuất tiện ích tiếp theo — chưa triển khai

1. **Outlook Calendar/Microsoft 365:** ưu tiên nếu sinh viên dùng tài khoản trường Office 365. Dùng cùng contract như Google: đọc busy/free, preview/confirm khi xuất ca tự học, không chỉnh lịch LMS. Microsoft Graph có calendar events và free/busy. [Calendar API](https://learn.microsoft.com/en-us/graph/api/resources/calendar?view=graph-rest-1.0).
2. **Google Tasks:** tùy chọn xuất checklist milestone để dùng trong workflow cá nhân. Không dùng tick hoàn thành làm bằng chứng hiểu bài; không thay assignment/grade trên LMS. Tasks API quản lý task/tasklist, nhưng `due` chỉ giữ ngày, không phù hợp để thay Calendar cho giờ/phút của study block. [API](https://developers.google.com/workspace/tasks/reference/rest), [Task due semantics](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks).

Chưa cần thêm Gmail đọc thư, mạng xã hội hay nhiều chatbot khác: không giúp trực tiếp vòng Plan–Do–Reflect và tăng phạm vi OAuth/data access.

Nguồn kỹ thuật: [Google event reminders](https://developers.google.com/workspace/calendar/api/v3/reference/events#reminders), [Push API](https://developer.mozilla.org/en-US/docs/Web/API/Push_API), [pywebpush](https://github.com/web-push-libs/pywebpush).
