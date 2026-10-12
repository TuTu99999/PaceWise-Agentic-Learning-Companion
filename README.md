# PaceWise

Demo chạy **PaceWise độc lập**, không cần API/web/database simulator. Tài khoản và dữ liệu cũ đã chuyển vào PostgreSQL PaceWise: [Hướng dẫn Docker và chuyển dữ liệu](docs/pacewise-standalone-migration.md).

Audit LMS simulator phục vụ Plan–Do–Reflect, chức năng đã sửa, kết quả test và giới hạn: [LMS simulator audit](docs/lms-simulator-pacewise-audit.md).

PaceWise là learning companion cho sinh viên theo chu trình **Plan → Do → Reflect**:

- **Plan:** lấy deadline/lịch học từ LMS, kết hợp lịch cá nhân, quỹ thời gian và ưu tiên để tạo study block khả thi.
- **Do:** chạy phiên tự học, ghi actual time, gợi ý học liệu có nguồn, hỏi đáp có citation và chặn yêu cầu làm hộ bài tính điểm.
- **Reflect:** phản tư sau hoạt động hoặc cuối tuần; đề xuất điều chỉnh, nhưng sinh viên vẫn xem và xác nhận trước khi đổi kế hoạch.
- **Instructor HITL:** hiển thị tín hiệu tổng hợp và hàng chờ cần con người xem; không dùng AI để tự chấm điểm hay tự đổi quy định học vụ.

Tài liệu kỹ thuật: [architecture diagram](docs/architecture_diagram.md) · [evaluation evidence](docs/evaluation-evidence.md).

## Chạy nhanh bằng Docker

Yêu cầu: Docker Desktop có Compose v2, Git và tối thiểu khoảng 4 GB RAM trống.

```powershell
git clone https://github.com/AI20K-Build-Phase-Cohort-4/P-008.git
cd P-008
Copy-Item .env.example .env
docker compose up --build -d --wait
docker compose ps
```

Mở:

| Thành phần | URL |
|---|---|
| PaceWise | <http://localhost:5173> |
| FastAPI Swagger | <http://localhost:8000/docs> |
| Backend health | <http://localhost:8000/health> |
| LMS Simulator | Đã tắt; giữ mã/volume cũ làm bản dự phòng, không cần cho demo |
| Qdrant dashboard | <http://localhost:6333/dashboard> |

Tài khoản demo LMS/PaceWise:

| Vai trò | Email | Mật khẩu |
|---|---|---|
| Sinh viên | `student@canvas.local` | `demo123` |
| Giảng viên | `teacher@canvas.local` | `demo123` |

Tài khoản trên là tài khoản demo đã được giữ qua migration; không đổi mật khẩu.
Trên server mới cần restore database PaceWise (cả schema `public` và `course_source`),
`data/course-source`, Qdrant và các khóa mã hóa/signing đang dùng. Không tự seed
hoặc ghi đè dữ liệu khi restart. Với thay đổi frontend/backend, rebuild service liên quan:

```powershell
docker compose up --build -d frontend backend worker
```

Xem log và dừng hệ thống:

```powershell
docker compose logs -f backend worker frontend
docker compose --env-file .env -f lms-simulator/docker-compose.yml logs -f lms-simulator
docker compose down
docker compose --env-file .env -f lms-simulator/docker-compose.yml down
```

`docker compose down` giữ nguyên volume. Chỉ dùng `docker compose down -v` khi chủ động muốn xóa toàn bộ dữ liệu local.

## Cấu hình `.env`

Tạo `.env` từ [`.env.example`](.env.example). Không commit `.env`, API key, token Canvas hoặc Google refresh token.

### Biến cốt lõi

| Biến | Khi nào cần | Mục đích |
|---|---|---|
| `OPENAI_API_KEY` | Khi chạy LLM thật | API key của OpenAI-compatible provider |
| `OPENAI_BASE_URL` | Khi chạy LLM thật | Base URL của provider/proxy |
| `MODEL_NAME` | Khi chạy LLM thật | Model cho coordinator và specialist workflows |
| `PACEWISE_API_KEY` | Luôn với LMS integration | Service key backend ↔ LMS; không đưa vào biến `VITE_*` |
| `PACEWISE_LAUNCH_SECRET` | Luôn | Ký one-time LMS launch token; tối thiểu 32 ký tự |
| `PACEWISE_SESSION_SECRET` | Luôn | Ký PaceWise session; tối thiểu 32 ký tự |
| `PACEWISE_DB_PASSWORD` | Docker/local | Mật khẩu PostgreSQL PaceWise |
| `LMS_DB_PASSWORD` | Docker/local | Mật khẩu PostgreSQL LMS Simulator |
| `DATABASE_URL` | Chạy backend ngoài Docker | Workspace, session, memory, queue và checkpoint |
| `LMS_BASE_URL` | Luôn | LMS adapter/simulator URL |
| `QDRANT_URL` | RAG | Vector store URL |

### Tùy chọn AI, calendar và vận hành

| Biến | Mặc định mẫu | Mục đích |
|---|---|---|
| `SEMANTIC_SAFETY_MODE` | `signals` | Phạm vi semantic safety classifier |
| `RAG_SCORE_THRESHOLD` | `0.72` | Ngưỡng evidence tối thiểu |
| `LLM_TIMEOUT_SECONDS` | `45` | Timeout một LLM request |
| `LLM_MAX_OUTPUT_TOKENS` | `800` | Giới hạn output |
| `APP_TIMEZONE` | `Asia/Ho_Chi_Minh` | Múi giờ học tập |
| `LMS_SYNC_INTERVAL_SECONDS` | `30` | Chu kỳ sync fallback/worker |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | trống | Google Calendar OAuth |
| `GOOGLE_TOKEN_ENCRYPTION_KEY` | trống | Fernet key mã hóa token |
| `LANGCHAIN_API_KEY` | trống | LangSmith tracing |
| `VITE_API_URL` | `/api/v1` | API URL mà frontend gọi |
| `VITE_LMS_URL` | `http://localhost:8010` | Đích của nút quay lại LMS |

Khi deploy, thay toàn bộ secret mẫu, bật HTTPS và đặt `SESSION_COOKIE_SECURE=true`, `FORCE_HTTPS=true`. Có thể dùng các biến `*_FILE` đã mô tả trong `.env.example` để mount secret.

## Chạy local không dùng Docker cho app

Yêu cầu Python 3.11 và Node.js 20+. PostgreSQL/LMS/Qdrant vẫn có thể chạy bằng Docker.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Trong terminal khác:

```powershell
cd frontend\pacewise
npm install
npm run dev
```

## Sample queries / thao tác demo

| Luồng | Input mẫu | Điều cần quan sát |
|---|---|---|
| Plan | Thêm lịch cá nhân `Ăn tối 18:00–18:45`, chọn ưu tiên, bấm **AI lập kế hoạch** | AI tránh giờ bận, tính capacity và chỉ tạo bản nháp |
| Plan | `Lập kế hoạch cho ba deadline gần nhất; mỗi phiên tối đa 60 phút.` | Nhiệm vụ được chia thành study block trước deadline |
| Do/RAG | `Theo slide TRR_Full_P4.pdf, quan hệ tương đương cần những tính chất nào? Trích nguồn.` | Trả lời có source/page hoặc báo chưa đủ nguồn |
| Guardrail | `Làm toàn bộ quiz tính điểm này để tôi nộp.` | Từ chối làm hộ và chuyển sang gợi ý từng bước |
| Understanding | `Quan hệ hai ngôi này có phản xạ và đối xứng nhưng không bắc cầu; nó có tương đương không?` | Phân tích theo rubric/evidence, không tự chấm điểm chính thức |
| Recover | `Tôi phát sinh việc bận 3 giờ tối nay; xếp lại nhưng không vượt deadline.` | 2–3 phương án, capacity/trade-off và preview trước xác nhận |
| Reflect | `Phiên này tôi mới hoàn thành 60%, vướng phần chứng minh và cần thêm 30 phút.` | Lưu actual/blocker; chỉ yêu cầu Plan phân tích lại khi có lệch |

Health/status không cần đăng nhập:

```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/api/v1/status
```

Các API nghiệp vụ yêu cầu PaceWise session, và request thay đổi trạng thái yêu cầu CSRF. Không truyền `user_id`, `role` hoặc `course_id` tùy ý từ client; backend lấy các giá trị này từ session đã ký.

## Endpoint chính

| Method | Endpoint | Chức năng |
|---|---|---|
| `GET` | `/health` | Health backend/checkpointer |
| `GET` | `/api/v1/status` | Agent status |
| `POST` | `/api/v1/chat` | Chạy LangGraph workflow |
| `POST` | `/api/v1/auth/lms-login` | Login local qua LMS |
| `POST` | `/api/v1/auth/lms-launch` | Đổi one-time launch token lấy session |
| `GET` | `/api/v1/auth/me` | Khôi phục session |
| `GET` | `/api/v1/lms/sync` | Snapshot LMS theo enrollment |
| `GET/PUT` | `/api/v1/workspace` | Đọc/lưu plan, lịch cá nhân, session, reflection |
| `GET` | `/api/v1/lms/events/stream` | SSE báo LMS thay đổi |
| `GET` | `/api/v1/instructor/overview` | Tổng quan lớp, instructor-only |
| `POST` | `/api/v1/instructor/actions` | HITL review/assessment/guidance |
| `GET/POST/DELETE` | `/api/v1/integrations/google-calendar/*` | Calendar OAuth/free-busy/events |
| `POST` | `/api/v1/calendar/pacewise-study-plan.ics` | Xuất plan `.ics` |
| `GET/POST/DELETE` | `/api/v1/notifications/push` | Trạng thái/đăng ký/hủy Web Push, student-only |
| `POST` | `/api/v1/notifications/claim` | Giới hạn chung và chống gửi trùng thông báo foreground |

## Kiểm thử

Backend:

```powershell
$env:DATABASE_URL='sqlite:///./tmp/pacewise-regression-test.db'
.\.venv\Scripts\python.exe -m ruff check src tests evals
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m evals.run_agent_eval
```

Frontend:

```powershell
cd frontend\pacewise
npm test -- --run
npm run build
```

Live external-model evaluation có thể gửi snapshot học tập demo đến provider được cấu hình. Chỉ chạy khi đã được phép chia sẻ payload và đã kiểm tra đích nhận:

```powershell
.\.venv\Scripts\python.exe -m evals.run_live_manual_evidence --case LIVE-01,LIVE-08,LIVE-12,LIVE-15,LIVE-19
```

Kết quả thực tế mới nhất: [docs/evaluation-evidence.md](docs/evaluation-evidence.md).

## Cấu trúc repository

```text
src/                         FastAPI, LangGraph, services, persistence
frontend/pacewise/           React + TypeScript + Vite
lms-simulator/               Canvas-compatible demo LMS
tests/                       Backend unit/integration/security tests
evals/                       Eval datasets, runners và raw reports
docs/                        Product/architecture/evaluation documents
observability/               Prometheus và Grafana provisioning
docker-compose.yml           Full local stack
```

## Giới hạn hiện tại

### Học liệu do LMS quản lý

- Trong LMS simulator: mở môn → **Files**, upload PDF/DOCX/PPTX/TXT/MD (tối đa 20 MB); **Replace file** tạo phiên bản mới; **Access** cấp/thu hồi quyền toàn lớp hoặc một sinh viên; **Delete** xóa tài liệu trên LMS.
- PaceWise worker đồng bộ file, kiểm tra checksum, trích text/chunks và index Qdrant. Bản gốc chỉ lưu ở LMS. File không đổi không được tải/index lại; worker reconciliation chạy mỗi 60 giây bên cạnh event sync.
- Giảng viên PaceWise xem trạng thái index trong **Tổng quan lớp**. Hai tab **Nội dung & học liệu** và **Cấu trúc môn học/nạp data** đã bỏ; dữ liệu KC/rubric cũ vẫn được giữ.
- Do gợi ý tài liệu có quyền truy cập. PDF mở tab mới qua proxy có session; chatbot lọc quyền + phiên bản trước khi dùng nguồn. Thu hồi quyền có hiệu lực với request mới ngay cả khi worker chưa xóa vector.
- API upload/delete học liệu trực tiếp PaceWise trả `410` mặc định. `ALLOW_LEGACY_MATERIAL_WRITES=true` chỉ là tùy chọn migration nội bộ, không nên bật khi deploy thông thường. Các API đọc tài liệu cũ vẫn được giữ.
- PDF scan chưa có OCR; link ngoài và định dạng không hỗ trợ không được tải/embedding tự động.

Áp dụng code mới vào Docker (không xóa volume):

```powershell
docker compose --env-file .env -f lms-simulator/docker-compose.yml up -d --build --wait
docker compose up -d --build backend worker frontend
```

Chi tiết kiểm thử và giới hạn: [LMS materials sync evaluation](docs/lms-materials-sync-evaluation.md).

- LMS production adapter/LTI cần developer key và sandbox của trường; simulator đang là nguồn demo chính.
- KPI nộp đúng hạn cần pilot nhiều tuần, không thể chứng minh chỉ bằng UI hoặc seed data.
- Live LLM/RAG eval phải được chạy với quyền chia sẻ dữ liệu rõ ràng; deterministic tests không thay thế SME review.
- PaceWise không làm hộ, tự nộp bài, tự chấm điểm hoặc tự gia hạn deadline.

### Nhắc học và nhịp học cá nhân

- Sinh viên → **Cài đặt**: bật/tắt nhắc deadline, bắt đầu Do, hoàn thành Reflect; chỉnh giờ yên lặng và giới hạn 1–3 thông báo/ngày. Icon chuông vẫn giữ nhắc trong ứng dụng.
- **Bật nhắc khi đóng tab** đăng ký Web Push sau khi người dùng cấp quyền. Cần HTTPS (hoặc localhost), backend và worker hoạt động. Thiết bị nhận push còn phụ thuộc trình duyệt/OS; việc cấp quyền không được tự động hóa.
- Nhắc Reflect sau 5 phút nếu chưa lưu; bài đã hoàn thành trên LMS hoặc phiên Do đã hoàn thành không bị nhắc bắt đầu lại.
- Khi xác nhận xuất kế hoạch sang Google, sự kiện **mới** có popup trước 15 phút. Các sự kiện đã xuất trước bản cập nhật vẫn được bỏ qua để không ghi đè lịch cũ.
- Nhịp học (mặc định 90 phút/10 phút nghỉ) dùng cho Plan Draft mới; không tự sửa lịch LMS hoặc kế hoạch đã xác nhận.
- Trạng thái Canvas/Google, lần đồng bộ gần nhất, lỗi và nút thử lại có trong Cài đặt.

Web Push dùng `WEBPUSH_ENABLED`, `WEBPUSH_PRIVATE_KEY_FILE`, `WEBPUSH_SUBJECT`. Development tạo khóa một lần tại `data/webpush-vapid.pem`; production phải cấp một khóa P-256 PEM ổn định, lưu bền vững và đặt contact VAPID thật. Không commit khóa hoặc subscription endpoint. Backend và worker phải dùng cùng khóa, volume, database. Các biến này đã có trong `.env.example`; không cần thêm một API key Google để dùng Web Push.

Chi tiết vận hành, kết quả test và giới hạn: [Student reminders evaluation](docs/student-reminders-integrations-evaluation.md).

### Bảo mật, SSO hai chiều và monitoring

PaceWise → **Quay lại LMS** mở phiên LMS simulator cùng người/role, không cần đăng nhập lại. LMS → PaceWise dùng launch code một lần. Logout PaceWise thu hồi phiên hiện tại và phiên LMS được liên kết; không phải logout mọi thiết bị.

```powershell
docker compose --profile observability up -d --build
```

Prometheus ở `http://localhost:9090`, Grafana ở `http://localhost:3001` (chỉ bind localhost). LangSmith là metadata-only, opt-in qua `LANGSMITH_ENABLED`/`LANGSMITH_API_KEY`; chưa bật cloud tracing mặc định. Chọn model ID thật qua `LLM_FAST_MODEL`/`LLM_REASONING_MODEL`. Cache và admission control hiện process-local, không phải chứng nhận tải 1.000 sinh viên.

Chi tiết test, SSO, privacy, KPI trước/sau và checklist production: [Security & observability evaluation](docs/security-sso-observability-evaluation-2026-10-09.md).

### Private API và Google quota guard

Frontend hiện dùng ECDH/HKDF/AES-GCM cho JSON request/response, gồm ID và target API path. Local bật `PRIVATE_API_REQUIRED=true`; plain JSON API cũ trả 426. Đây không thay thế HTTPS và không giấu dữ liệu đã giải mã khỏi chủ trình duyệt. Browser cần HTTPS/localhost; API upload FormData legacy không đi qua gateway.

Google Calendar có limiter database dùng chung: mặc định project 1500/phút, user 60/phút, budget 50000 trong cửa sổ ngày bảo thủ, tối đa 16 outbound đang chạy. Cache 5 phút, khóa chống sync trùng, retry bounded và event ID ổn định. Đặt thấp hơn quota thực tế của project; không giả định mọi usage sẽ luôn miễn phí.

Sau rebuild **Ctrl+F5**. Chi tiết khóa bền vững, test và giới hạn: [Private API & Google quota evaluation](docs/private-api-google-quota-evaluation-2026-10-09.md).
