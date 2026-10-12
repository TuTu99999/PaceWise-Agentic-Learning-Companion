# Bảo vệ dữ liệu, SSO hai chiều và observability — 09/10/2026

## Kết luận và phạm vi

Đã sửa đăng nhập/đăng xuất, triển khai cầu nối **PaceWise ↔ LMS simulator** cho cả sinh viên và giảng viên, cập nhật Docker local và kiểm tra bằng HTTP thật trên PostgreSQL. Không thay đổi scope sản phẩm **Plan → Do → Reflect**; Assessment vẫn nằm trong Do.

Đã triển khai highlight ngày hiện tại, KPI trước/sau dạng quan sát, model routing/cache/admission control, Prometheus/Grafana và trace LangSmith chỉ chứa metadata. Đây **không** phải chứng nhận bảo mật, FERPA compliance, bằng chứng cải thiện giáo dục hoặc cam kết chịu tải 1.000 người dùng thật.

## 1. Đăng nhập và dữ liệu truyền

- Cookie phiên ứng dụng là HttpOnly; không trả bearer access token cho JavaScript của LMS. Cookie CSRF không phải credential đăng nhập và cần được frontend đọc để gửi header.
- Validation lỗi không trả lại `input` chứa mật khẩu. Lỗi 5xx và exception middleware không trả traceback, khóa API hoặc thông báo provider nguyên văn.
- API nhạy cảm dùng `Cache-Control: no-store, private`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`.
- Access log Nginx không ghi query string; tắt access log mặc định Uvicorn để không ghi OAuth code. Error log của request, RAG và worker chỉ ghi loại lỗi và ID kỹ thuật, không ghi raw exception chứa thông tin kết nối.
- Model telemetry không ghi prompt/câu trả lời. LangSmith native auto-tracing bị tắt vì có thể xuất nguyên graph state.
- Danh sách người dùng LMS chỉ trả trường directory cần thiết trong phạm vi lớp liên quan, không trả email toàn hệ thống. Tổng quan lớp kiểm tra lại enrollment giảng viên hiện tại.
- Payload dành cho người đang đăng nhập vẫn có tên/email và dữ liệu chính họ được phép xem. Không thể và không nên “giấu tất cả JSON” khỏi DevTools của chính người dùng. Bảo vệ đúng là **HTTPS khi deploy, kiểm tra quyền trên server, tối thiểu hóa payload và không gửi secret**.

Lưu ý: directory bị thu hẹp không còn là cơ chế tìm mọi người chưa ghi danh; quản lý enrollment phải nằm ở LMS với quyền phù hợp. Không thêm API toàn hệ thống chỉ để phục vụ dropdown.

## 2. SSO hai chiều, không truyền mật khẩu qua URL

```text
PaceWise đã đăng nhập
→ bấm “Quay lại LMS”
→ backend dùng service credential xác nhận user/course/role hiện tại
→ LMS phát code ngẫu nhiên, một lần, hạn 60 giây
→ browser POST form vào LMS (không đưa code lên URL)
→ LMS kiểm tra Origin + enrollment, tạo cookie và mở lớp
→ từ LMS mở PaceWise bằng launch code ngẫu nhiên
→ backend xác minh code server-to-server
→ giữ phiên PaceWise cũ nếu cùng người/role và phiên còn hợp lệ
```

- Browser không tự chọn user ID hoặc role; backend lấy từ phiên đã xác thực.
- Origin phải khớp `PACEWISE_URL`; cả hai chiều kiểm tra code đã dùng/hết hạn và quyền hiện tại.
- Link LMS → PaceWise dùng `/app#/launch`, không quay về landing page. Token không còn là JWT mang tên/email; frontend xóa launch code khỏi thanh địa chỉ ngay khi nhận.
- Hai chiều dành cho **simulator hiện tại**. Tích hợp Canvas production cần adapter/SSO được trường cho phép, không có nghĩa tự đăng nhập vào Canvas thật bằng service key demo.

## 3. Logout thật và giới hạn phạm vi

Logout thu hồi row phiên PaceWise trong database, xóa cookie, hủy đăng ký push của phiên và yêu cầu LMS thu hồi phiên được tạo qua cầu nối này. Cookie cũ dùng lại trả 401. SSE kiểm tra lại session trước khi phát dữ liệu/heartbeat.

Frontend chỉ xóa state và chuyển về login sau khi backend xác nhận. Nếu request thất bại, không giả vờ logout. Nếu server đã thu hồi nhưng browser storage bị chặn, giao diện vẫn logout; không để lỗi dọn cache che mất kết quả thật. Các tab khác nhận tín hiệu đổi auth không chứa PII; trang được khôi phục từ bfcache tải lại trạng thái.

Nếu LMS không phản hồi, PaceWise vẫn logout và báo chưa xác nhận thu hồi LMS. Đây là **logout phiên hiện tại và phiên LMS liên kết**, không phải “đăng xuất mọi thiết bị”, cũng không thu hồi tất cả phiên LMS độc lập đã đăng nhập trước đó.

## 4. Lỗi 502 local

Frontend Nginx từng giữ địa chỉ container backend cũ sau recreate. Đã dùng Docker DNS resolver `127.0.0.11`, TTL 5 giây và upstream động cho API/SSE. Sau recreate backend, HTTP đăng nhập và SSO vẫn thành công. Lỗi upstream vẫn có thể xảy ra khi backend đang khởi động hoặc ngừng chạy; thông báo cho người dùng được rút gọn, không lộ raw lỗi server.

## 5. Ngày hiện tại và dashboard giảng viên

- Lịch tuần/tháng ở sinh viên và lịch chỉ xem của giảng viên highlight ngày hiện tại bằng indigo nhẹ: light `#F5F7FF`/`#E7EDFF`, dark nền xanh đậm. Có nhãn “Hôm nay” và `aria-current="date"`.
- Ngày lấy theo `Asia/Ho_Chi_Minh`, cập nhật mỗi phút/khi tab hiện lại. Mốc **demo planner 05/10/2026** vẫn được giữ theo yêu cầu trước; không giả rằng ngày thực tế luôn là ngày demo.
- Giữ cảnh báo nguy cơ trễ và nhóm ẩn danh tối thiểu 5 sinh viên; không thêm lại tab phản hồi/can thiệp đã yêu cầu bỏ.
- Thêm `adoptionComparison`: so sánh **cùng nhóm sinh viên có cả dữ liệu trước và sau lần đăng nhập PaceWise đầu tiên**. Deadline dùng timestamp và override từng sinh viên; deduplicate submission, dùng lần nộp đầu nếu có, bỏ excused/future/unpublished và không coi timestamp thiếu là nộp đúng hạn.
- Mỗi giai đoạn: tỷ lệ = số nhiệm vụ nộp đúng hạn / số nhiệm vụ hợp lệ đã tới deadline. Delta tính theo **điểm phần trăm**, không phải phần trăm tương đối.
- Nhóm không đủ 5 sinh viên có cả hai giai đoạn trả `insufficient_data`. Không sinh số cải thiện từ seed hoặc LLM.
- `causalClaim=false`: so sánh quan sát không chứng minh PaceWise gây ra cải thiện; dữ liệu và workload hai giai đoạn có thể khác nhau. Cần pilot/control group để đánh giá tác động.

## 6. Liêm chính, grounding và kiểm soát model

### Guardrails

Giữ rule + semantic safety theo cơ chế hiện có, bổ sung nhận diện yêu cầu tiếng Việt “giải giúp”. Không có tài liệu môn học được phép dùng thì chatbot trả thiếu nguồn trước khi gọi LLM. Retrieval kiểm tra quyền/phiên bản hiện tại và kiểm tra citation sau đáp án, kể cả khi dùng cache. Không claim mọi cách lách guardrail đều bị chặn.

### Routing và cache

- `LLM_FAST_MODEL`: hỏi đáp đơn giản, coordinator, safety, question design.
- `LLM_REASONING_MODEL`: Plan, Assessment, Reflect, Recover hoặc QA phức tạp.
- Hai biến để trống → dùng model đang cấu hình; **không tự tạo model rẻ hơn hoặc khẳng định tiết kiệm khi chưa có model ID/giá thật**.
- Cache exact cho QA, TTL mặc định 300 giây, tối đa 256 entry. Khóa chứa phạm vi user/institution/course, nguồn/phiên bản, model, prompt và policy; không dùng chung đáp án qua quyền truy cập khác nhau. Trả bản copy để caller không sửa cache.
- Không cache chấm Assessment, Reflect, Plan hoặc quyết định re-plan.
- Admission mặc định tối đa 8 model invocation đang chạy, 32 đang chờ, timeout chờ 1 giây. Quá tải bị từ chối có kiểm soát thay vì xếp hàng vô hạn.
- Đây là **process-local**; nhiều replica cần quota/cache phân tán, rate limit theo người dùng, budget và retry/backoff phù hợp provider.

### Test tải kỹ thuật

1.000 request tổng, 64 thread client, provider giả lập; cấu hình active=4/waiting=4. Lần chạy mục tiêu ghi nhận **64 accepted / 936 rejected / peak provider=4**. Số accepted thay đổi theo scheduler máy, invariant cần giữ là peak≤4 và slot trả lại đầy đủ.

Test này chứng minh cơ chế chống overload, **không** chứng minh 1.000 request đồng thời đều được phục vụ, latency provider thật hoặc giá tiền thực tế. Cần benchmark full HTTP với dữ liệu/LLM được phép sử dụng trước khi tuyên bố capacity production.

## 7. Observability và cấu hình vận hành

```powershell
docker compose --profile observability up -d --build
```

- PaceWise: `http://localhost:5173/app#/login`
- LMS simulator: `http://localhost:8010`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001`

Prometheus/Grafana bind localhost. Dashboard có HTTP/agent/RAG latency, histogram p95, routing, cache hit/miss, admission rejected/timeout, active/waiting, token/estimated cost và trace delivery. Ba alert: backend down, tỷ lệ lỗi server, model overload. Histogram dùng cumulative bucket và TYPE hợp lệ, đã sửa lỗi làm Prometheus không parse được. Thiết kế bucket bám [Prometheus histogram guidance](https://prometheus.io/docs/practices/histograms/).

Production `/metrics` cần `METRICS_BEARER_TOKEN`, scrape qua mạng riêng. Prometheus production phải cấu hình `authorization.type: Bearer` và `credentials_file` được mount từ secret; config demo hiện không tự inject token. Không bật production token rồi giữ scraper demo không có authorization.

LangSmith **opt-in**, nhập các biến sau vào `.env`, không commit key:

```ini
LANGSMITH_ENABLED=true
LANGSMITH_API_KEY=<key của bạn>
LANGSMITH_PROJECT=pacewise-private-metadata
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_TRACING_V2=false
```

Ứng dụng chỉ gửi span ID, tên node/task do ứng dụng định nghĩa, thời gian, outcome và loại lỗi. `inputs={}`; không gửi câu hỏi, bài làm, user ID, email, token hoặc raw error. Queue nền bounded 128; mạng/SDK lỗi không chặn request học. Sử dụng [LangSmith Client API](https://reference.langchain.com/python/langsmith/client/Client) với input redaction và payload allowlist.

**Cập nhật sau khi cấu hình key/workspace:** đã kiểm chứng đọc lại 5 span hoàn chỉnh của backend và 5 span của worker từ LangSmith cloud thật, đúng project/hierarchy, inputs rỗng và outputs chỉ có trạng thái. Xem [báo cáo kết nối LangSmith](langsmith-connection-evaluation-2026-10-09.md). Native tracing vẫn tắt để không gửi raw graph state. Đây là connectivity smoke, không phải evaluation toàn bộ workflow hay capacity 1.000 SV.

`LLM_INPUT_COST_PER_MILLION` và `LLM_OUTPUT_COST_PER_MILLION` phải điền giá phù hợp provider. Mặc định 0 nghĩa chưa biết giá, không phải miễn phí. Routing nhiều model cần bảng giá theo model trước khi xem estimated cost là số chính xác.

Khi deploy: HTTPS, `SESSION_COOKIE_SECURE=true`, secrets riêng đủ mạnh, đổi password admin Grafana, đóng port DB/Qdrant và chỉ mở reverse proxy. Compose local hiện vẫn publish các port DB cho demo; chưa là cấu hình hardened production.

## 8. Evidence kiểm thử

| Kiểm tra | Output thực tế | Evidence |
|---|---|---|
| Backend full regression, SQLite riêng | 535 passed | [JUnit backend](../evals/reports/security-observability-backend-2026-10-09.xml) |
| LMS simulator | 67 passed, 1 dependency deprecation warning | [JUnit LMS](../evals/reports/security-simulator-2026-10-09.xml) |
| Frontend | 204 passed / 51 files | [JUnit frontend](../evals/reports/security-frontend-2026-10-09.xml) |
| Docker production frontend build | passed, main chunk 348.00 kB / gzip 110.37 kB | Build stdout, không có warning chunk >500 kB |
| Student SSO hai chiều | login 200 → bridge 303 → return 200 | [Runtime snapshot](../evals/reports/security-sso-runtime-2026-10-09.json) |
| Instructor SSO hai chiều | login 200 → bridge 303 → return 200 | Runtime snapshot |
| Code đã dùng lại | 401, cả hai role | Runtime snapshot |
| Cookie PW cũ sau logout | 401, cả hai role | Runtime snapshot |
| LMS liên kết sau logout PW | 401, cả hai role | Runtime snapshot |
| Invalid password validation / secret upstream | Không trả secret giả lập | `tests/test_api/test_auth_privacy.py` |
| Browser storage bị chặn / network logout lỗi | Server success vẫn logout; network lỗi không fake logout | `AppShell.test.tsx` |
| Giảng viên mất enrollment | 403 | `test_instructor_overview_rechecks_live_enrollment` |
| Prometheus/Grafana | target `up`, lastError rỗng, Grafana health 200 | Runtime snapshot; promtool success / 3 rules |

SSO smoke là HTTP thật, không phải kiểm tra trực quan browser. Chạy lại bằng:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_auth_bridge.py
```

Runner dùng hai tài khoản demo công khai, chỉ tạo/thu hồi phiên test; không in cookie/code/password người dùng thật hoặc xóa kế hoạch. Không dùng runner demo này làm production account healthcheck.

## 9. Các phần trước vẫn được giữ

Google export nhắc trước 15 phút, cấu hình deadline/Do/Reflect, giờ yên lặng, Web Push opt-in, nhịp học và trạng thái kết nối đã có trong [reminder evaluation](student-reminders-integrations-evaluation.md). Người dùng vẫn phải cấp quyền thông báo và Google OAuth; không tự bật quyền thiết bị. Các sự kiện Google cũ không bị ghi đè hàng loạt.

Chưa đánh giá: pilot sinh viên thật, causal improvement, 1.000 concurrent thật, pentest độc lập và Canvas production SSO. LangSmith cloud delivery đã được kiểm chứng riêng bằng synthetic connectivity spans, chưa benchmark trace loss/throughput khi tải lớn. Các giới hạn này không được gộp vào kết luận “test pass = toàn bộ kiến trúc production đã hoàn thiện”.
