# Tách Docker LMS — evaluation 10/10/2026

## Phạm vi đã chốt

Demo chỉ mở web PaceWise; LMS **API/database vẫn chạy nội bộ**, không phải loại bỏ nguồn LMS. Không deploy AWS trong tác vụ này. Hướng dẫn vận hành: [PaceWise-only Docker](pacewise-only-demo-docker.md).

## Kết quả

| Kiểm tra | Kết quả / evidence |
|---|---|
| Backend regression và Compose contracts | **684 passed**, [JUnit](../evals/reports/pacewise-only-backend-2026-10-10.xml) |
| Frontend regression | **319 passed / 69 files**, [JUnit](../evals/reports/pacewise-only-frontend-2026-10-10.xml) |
| Simulator regression, gồm API-only/web restore policy | **87 passed**, [JUnit](../evals/reports/lms-api-only-simulator-2026-10-10.xml) |
| TypeScript + Vite build | Passed; Docker frontend build có `VITE_LMS_WEB_ENABLED=false` |
| Compose default/optional overrides | Cả 4 cấu hình `config --quiet` passed; không xuất cấu hình secret |
| Browser thật, mobile sinh viên 390×844 | Login, tải dữ liệu, reload giữ phiên, không có nút LMS, logout: passed |
| Browser thật, desktop giảng viên 1366×900 | Login, đọc profile, mở quản lý nhiệm vụ, không có nút LMS, logout: passed |
| Request browser tới LMS port 8010 | **0 cho cả hai role**; [script](../scripts/evaluate_pacewise_only_demo.cjs) |
| Kết nối từ backend sang API LMS | `/api/health` **200**; `/` và `/docs` **404** |
| Cổng public của LMS/API database | Không có published port; chỉ `8010/tcp` và `5432/tcp` nội bộ |
| Quyền sở hữu stack | Root project không còn LMS service/volume; project riêng chứa đúng 2 services |
| Network service | `internal=true`; chỉ LMS API, backend PaceWise, worker PaceWise tham gia |
| Giữ dữ liệu | Trước/sau: **29 users, 3 courses, 94 assignments**; tái dùng đúng database/uploads volume |
| Worker sau chuyển network | Chạy; không có ERROR/Traceback/failed trong cửa sổ log 3 phút kiểm tra |

Hai container cũ `pacewise-lms-simulator-1` và `pacewise-lms-postgres-1` được dừng rồi gỡ sau khi stack mới khỏe. **Không xóa volume hoặc dữ liệu**. Volume LMS khai báo `external` để Compose không quản lý việc xóa; trên máy mới phải tạo hai volume trước.

## Cách chạy test đáng tin cậy

Backend suite phải chạy trên database test riêng, không dùng `.env` deployment. Lần chạy đầu bị lẫn cấu hình local: 5 kiểm tra pool dùng kết nối không phù hợp với SQLite fixture và 1 kiểm tra tracing opt-in bị tracing môi trường bật sẵn. Đã chạy lại toàn suite trên SQLite riêng, tracing tắt, đạt 684/684; không sửa code Calendar/tracing để làm test qua và không thay đổi `.env` người dùng.

```powershell
$env:DATABASE_URL='sqlite:///./data/pacewise-only-tests-20261010.db'
$env:APP_ENV='test'
$env:LANGSMITH_ENABLED='false'
$env:LANGCHAIN_TRACING_V2='false'
$env:PRIVATE_API_REQUIRED='false'
$env:FORCE_HTTPS='false'
$env:SESSION_COOKIE_SECURE='false'
.\.venv\Scripts\python.exe -m pytest tests -q
```

Các biến trên chỉ đặt trong shell test, không sửa cấu hình container. Browser smoke dùng tài khoản demo có sẵn; không gọi LLM, không tạo/sửa nhiệm vụ/profile hoặc áp dụng kế hoạch.

## Giới hạn

- Đây là xác nhận tách Docker và vận hành demo local, không phải kiểm chứng tải 1.000 người hay hiệu quả học tập.
- Backend/worker vẫn phụ thuộc LMS API; tắt cả stack LMS sẽ làm login/authoring/sync không hoạt động.
- Override mở lại web LMS đã được kiểm tra cấu hình và policy bằng test; **không bật web LMS trong runtime demo cuối cùng**.
- Không công khai cổng LMS/database. Trước deploy production cần secret mạnh, HTTPS, cấu hình callback, backup và giới hạn các cổng local của PaceWise theo [hướng dẫn](pacewise-only-demo-docker.md).
