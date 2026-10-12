# Xác nhận phần lịch hợp lệ — 10/10/2026

## Hành vi đã triển khai

Thiếu capacity không đồng nghĩa mọi ca đã xếp đều không học được. PaceWise vẫn giữ chu trình **Plan → Do → Reflect**, không thêm agent hoặc phase.

- Xác nhận toàn bộ vẫn cần vượt qua hard quality gate.
- Khi toàn kế hoạch chưa khả thi, backend tính một tập ca có thể xác nhận riêng. Frontend phải hiển thị preview và sinh viên xác nhận rõ phần này.
- Backend dùng bản nháp do server lưu, assignment/deadline và lịch LMS mới nhất, lịch cá nhân/giấc ngủ/thời gian rảnh đã lưu. Không tin danh sách ca hoặc kết quả kiểm tra do client tự tạo.
- Ca quá khứ, vượt deadline tới giờ/phút, trùng ca, trùng lịch bận, ngoài giờ rảnh, task không tồn tại/đã nộp, dependency thiếu/sai thứ tự/vòng lặp đều bị loại.
- Khi prerequisite bị loại hoặc chưa xếp đủ công việc, các bước phụ thuộc cũng không được mở. Bộ chọn lặp tới khi tập ca còn lại vượt qua validator độc lập.
- UI cho xem **Lịch đang dùng / Bản nháp**. Tạo hoặc xem bản nháp mới không thay thế lịch đã xác nhận.
- Ca hợp lệ chưa xác nhận có nút **Xem và xác nhận phần lịch hợp lệ**. Ca được xác nhận có **Bắt đầu Do**. Ca lỗi hiện nút vô hiệu hóa và lý do bằng tiếng Việt.
- Lưu canonical response từ backend, không tự lưu bản nháp cũ khi xác nhận. Retry xác nhận trả lại bản đã xác nhận, không tạo phiên bản trùng.

## Không che giấu rủi ro

Xác nhận một phần không biến `feasibility.feasible` thành `true`. Bản xác nhận giữ:

- `confirmation.mode = partial` và acknowledgement;
- danh sách ca được phép và ca bị loại;
- thiếu bao nhiêu phút theo từng task; deadline/nguồn nhiệm vụ vẫn có trong dữ liệu kế hoạch và LMS;
- toàn bộ milestone, planning target, rubric/KC và estimate;
- `outstanding_plan_work` trong learner memory và audit `PLAN_CONFIRMED`.

Công việc của ca bị loại được cộng lại vào phần chưa xếp đủ; không âm thầm giảm scope, sửa estimate, đánh dấu hoàn thành hay đổi deadline LMS. Lịch đã xác nhận một phần vẫn hiện cảnh báo thiếu thời gian khi quay về từ Do. Reflect/Plan tiếp tục dùng luồng tiến độ và tái lập kế hoạch hiện có; việc xác nhận một phần **không tự động re-plan**.

## Kiểm thử và kết quả

| Bộ kiểm thử | Kết quả | Phạm vi |
| --- | --- | --- |
| Backend pytest toàn bộ | 676 passed | Independent quality gate, subset selection, API confirmation, audit/memory, timer Do và regression |
| Frontend Vitest toàn bộ | 309 passed | UI review, nút Do, giữ lịch đang dùng, canonical persistence và regression |
| Browser xác nhận một phần | 9 passed | 390×844, 662×432, 1366×900; 3 case trên mỗi kích thước |
| Browser responsive lịch | 19 passed | Bố cục/cuộn lịch sinh viên và giảng viên |
| TypeScript + production build | PASS | `npm.cmd run build` |

Đã rebuild/recreate backend và frontend Docker local, không reset database. Kiểm tra sau cập nhật: cả hai container `healthy`; `GET localhost:8000/health` và `GET localhost:5173/app.html` trả HTTP 200.

Acceptance cases trọng tâm:

1. Thiếu 9 giờ vẫn review/xác nhận được ca an toàn; trước khi bấm xác nhận chưa có API ghi dữ liệu.
2. Ca vượt hạn 12:00 không được mở Do; không có cách dùng xác nhận một phần để bỏ qua lỗi này.
3. Hai ca trùng nhau bị loại bảo thủ; công việc còn thiếu không biến mất.
4. Dependency chưa xếp, chưa đủ phút hoặc vòng lặp không mở được bước sau; loại prerequisite lan truyền tới các bước phụ thuộc.
5. Thay đổi lịch LMS sau preview làm xác nhận thất bại và giữ bản nháp để phân tích lại.
6. Danh sách block bị giả mạo không được xác nhận; API yêu cầu acknowledgement và đúng tập ca server vừa kiểm tra.
7. Retry xác nhận không tạo trùng; ca bị loại không mở timer, ca an toàn đã xác nhận mở được timer Do qua API.
8. Bản nháp mới không che mất ca cũ đã xác nhận. Ước lượng/số phút nhiệm vụ gốc không bị thay khi xác nhận.
9. Đổi thời gian rảnh làm ca nằm ngoài khung bị loại; giờ tự học ưu tiên được xét như một cửa sổ hợp lệ, không như lịch bận.

Raw artifacts:

- [Backend JUnit](../evals/reports/partial-plan-backend-2026-10-10.xml)
- [Frontend JUnit](../evals/reports/partial-plan-frontend-2026-10-10.xml)
- [Browser partial-plan results](../evals/reports/partial-plan-ui-2026-10-10/results.json)
- [Mobile preview screenshot](../evals/reports/partial-plan-ui-2026-10-10/390-844-review.png)
- [Responsive calendar results](../evals/reports/partial-plan-responsive-2026-10-10/results.json)

## Cách tái lập

Backend: chạy pytest với `APP_ENV=test`, `PRIVATE_API_REQUIRED=false`, `LANGSMITH_ENABLED=false` và database SQLite riêng cho test; không dùng database học viên thật.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Frontend:

```powershell
cd frontend\pacewise
npm.cmd test -- --run
npm.cmd run build
```

Browser: chạy Vite QA ở `127.0.0.1:5174`, cài Playwright ngoài repo hoặc đặt `PLAYWRIGHT_MODULE` tới module đã cài, rồi chạy từ root repo:

```powershell
node scripts/evaluate_partial_plan.cjs
$env:CALENDAR_ONLY='true'
$env:RESPONSIVE_REPORT_DIR='evals/reports/partial-plan-responsive-2026-10-10'
node scripts/evaluate_responsive_ui.cjs
```

## Giới hạn bằng chứng

- Browser dùng API fixture tổng hợp. Backend API được kiểm tra riêng bằng pytest; không giả rằng đây là phiên học người thật hoặc test LLM production.
- Kiểm tra dependency bảo thủ: một ca quá khứ không tự chứng minh prerequisite đã hoàn thành; trường hợp không có bằng chứng/ca tiên quyết hợp lệ cần phân tích lại.
- Bản nháp cũ chưa có metadata preview hoặc tập ca đã thay đổi theo thời gian có thể cần **AI phân tích lại** trước khi xác nhận.
- Không chứng minh hiệu quả học tập, nộp đúng hạn hay tải 1.000 người đồng thời từ các test này.
