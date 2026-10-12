# Nhịp học theo môn và loại hoạt động — 10/10/2026

Scope vẫn là **Plan → Do → Reflect**. Không thêm agent, không để LLM đoán khả năng tập trung. Đây là phần nối tiếp [độ tin cậy phiên và nhịp học v1](study-rhythm-evaluation-2026-10-10.md).

## Luồng đã triển khai

1. **Lựa chọn ban đầu:** Settings → Nhịp học cá nhân. Mặc định 90 phút học / 10 phút nghỉ là cấu hình sản phẩm, không phải thời lượng tối ưu khoa học. Sinh viên chỉnh mặc định hoặc lưu nhịp riêng theo môn và hoạt động: học khái niệm, luyện tập vận dụng, lập trình, ôn tập. Không đủ dữ liệu thì giữ lựa chọn này.
2. **Quan sát:** Do dùng timer server/checkpoint, pause/resume và retry idempotent đã có. Hoàn thành phiên lưu nguyên nhân gián đoạn, cảm nhận độ dài, tiến độ, nhịp của ca đã xác nhận, loại hoạt động, readiness và Assessment evidence. Đổi preference sau đó không viết lại lịch sử. Việc đột xuất không làm giảm Knowledge State hoặc tăng estimate công việc.
3. **Thử nhịp khác:** rule `rhythm-rule-v2-course-activity` chỉ tạo đề xuất có source refs và phạm vi môn/hoạt động cụ thể. Sinh viên phải xác nhận; confirm không sửa lịch, estimate hay Knowledge State. Workspace versioned autosave lưu lựa chọn riêng, không thay mặc định hoặc môn/hoạt động khác.
4. **Plan chia ca:** milestone → activity label → chọn nhịp đúng môn/hoạt động → scheduler deterministic. Ca lưu `activityType`, `activitySource`, `rhythm`, work và checkpoint budget. Nghỉ/checkpoint được tính trước deadline; thay nhịp không giảm tổng work. Phân tích lại và xác nhận preview mới mới đổi lịch đang áp dụng.
5. **Theo dõi:** bảng trước/sau tách tỷ lệ hoàn thành ca, báo phiên dài, phiên có Assessment dùng hint, cùng kết quả conceptual/application/transfer/retention. Chưa test một dimension ghi “chưa kiểm tra”; không suy ra hiểu bài từ hoàn thành ca hay số phút.

## Phạm vi và điều kiện đề xuất

- Ít nhất **3 session ID riêng biệt**, cùng môn, task, loại hoạt động, readiness, nhịp và checkpoint budget. Tối đa 5 phiên gần nhất được trích nguồn.
- Chỉ dùng thời gian timer, không gap chưa quan sát; reason `none` hoặc `fatigue`; nhiều lần báo `long`/`too_long`.
- Ca đã xếp phải dài ít nhất bằng cap hiện tại. Ca đã ngắn do milestone không được dùng để kết luận cap lớn cần giảm.
- Thực học ít nhất 75% cap, hoặc ít nhất `max(20 phút, 50% cap)` khi báo mệt. Một phiên khó, gián đoạn đột xuất, tự khai báo hoặc thiếu dữ liệu không đủ để đề xuất.
- Thử giảm cap 15 phút, sàn 20 phút, giữ nghỉ và tổng work. Không tự tăng/giảm bất kỳ preference nào.
- Ngưỡng trên là **engineering policy**, chưa calibration bằng sinh viên thật. Đề xuất là thử nghiệm nhỏ, không phải “nhịp tối ưu” hay chứng minh hiệu quả giáo dục.
- Assessment độc lập chỉ tổng hợp evidence được chấp nhận, có KC/source ID, không dùng hint. Theo từng KC, latest attempt; KC khác trả lời đúng không che failure còn tồn tại. Số phiên có dùng hint được hiển thị riêng, không biến thành mastery.

### Nhận diện hoạt động

Không đoán từ tên môn, persona hoặc thời gian đã học. Dùng action rõ trong milestone (ví dụ “đọc slide”, “viết code”, “làm bài tập”, “ôn tập”) hoặc metadata assignment có loại hoạt động hợp lệ. Nguồn nhận diện được lưu; nếu mơ hồ/đa loại thì `unknown` và dùng mặc định, không tạo đề xuất tự động cho dữ liệu ấy.

Đây là classifier rule bảo thủ, **không bảo đảm nhận diện mọi cách diễn đạt**. Ca legacy không có loại hoạt động không bị gán nhãn hồi tố; cần một bản Plan mới có context rõ. Course-scoped preference không có nghĩa tự động áp dụng cho một task chưa xác định loại.

## Test/evaluation thực tế

Các test sau dùng fixture kỹ thuật, không phải kết quả pilot người học.

| Case | Output kiểm tra |
|---|---|
| Nhịp riêng không truyền chéo | Cùng sinh viên: môn 1 conceptual = 60 phút, coding = 75; môn 2 conceptual và unknown = mặc định 90 |
| Thiếu/khác loại bằng chứng | 2 concept + 1 coding/unknown/khác môn → không proposal |
| Mệt giữa phiên | 1 phiên dừng ở 30/60 phút → không proposal; 3 phiên tương đồng, báo mệt/quá dài → thử 45/10, vẫn cần xác nhận |
| Ca vốn ngắn | Cap 60 nhưng ca 20 hoặc 45 phút → không tự giảm cap chỉ từ các ca ấy |
| Estimate không mượn hoạt động khác | Lịch sử coding đầy đủ có bounded factor 1.75 → P50 53 cho coding baseline30; conceptual baseline30 vẫn30 |
| Timer lưu đúng ca đã xác nhận | Ca coding đã xác nhận40/5 và checkpoint5; preference sau đó120/20 → timer/evaluation vẫn40/5 và checkpoint5 |
| Không giảm tổng việc | Target120 → tổng work120 với cap60/75/90, từng ca không vượt cap được chọn |
| Deadline tính cả nghỉ | Work10, cap20, checkpoint15, nghỉ10: 15:00–15:20 và15:30–15:50; hạn15:30 → infeasible |
| Chưa xác nhận | GET không đổi workspace/plan; confirm trả phạm vi môn/hoạt động, `planChanged=false`; reducer giữ plan và mặc định |
| Lưu/reload | Browser390 và1366: concept môn1 =45; coding môn2 =75 sau reload; concept môn2 vẫn mặc định60 |
| Hiểu bài không đồng nghĩa hoàn thành | Ca hoàn thành100% nhưng application pass rate0; retention chưa test → “chưa kiểm tra”, không “đã hiểu” |
| Phân quyền/schema | Course ngoài enrollment →403; trùng scope hoặc loại unknown trong override → validation error; legacy duration null/NaN/string → abstain, không crash |

Kết quả chạy lại:

- **659 backend test pass** — [JUnit](../evals/reports/activity-rhythm-backend-2026-10-10.xml).
- **305 frontend test pass / 68 files** — [JUnit](../evals/reports/activity-rhythm-frontend-2026-10-10.xml).
- **16/16 browser checks** ở390×844 và1366×900 — [JSON](../evals/reports/activity-rhythm-ui-2026-10-10/results.json), [mobile](../evals/reports/activity-rhythm-ui-2026-10-10/390-settings.png), [desktop](../evals/reports/activity-rhythm-ui-2026-10-10/1366-settings.png).
- Calendar native wheel/touch regression **6/6**, hai role ở390×844,662×432,844×390; đều tới giờ cuối lịch.
- TypeScript và production build thành công.
- Docker backend/frontend đã rebuild/recreate, đều `running healthy`; `/health`8000 và `/app`5173 trả200. Import runtime trả `rhythm-rule-v2-course-activity`, schema chứa `activityRhythms`. Không chỉnh dữ liệu thật để tạo test evidence; giữ nguyên các dịch vụ khác. Vite QA5174 đã dừng sau test.

Chạy lại từ repo root (PowerShell):

```powershell
$env:APP_ENV = 'test'
$env:PRIVATE_API_REQUIRED = 'false'
$env:LANGSMITH_ENABLED = 'false'
$env:DATABASE_URL = 'sqlite:///./evals/reports/activity-rhythm-' + [guid]::NewGuid().ToString() + '.db'
.\.venv\Scripts\python.exe -m pytest tests -q --junitxml=evals/reports/activity-rhythm-backend-2026-10-10.xml
npm.cmd --prefix frontend/pacewise test -- --run
npm.cmd --prefix frontend/pacewise run build
```

Browser: chạy Vite QA ở5174, cài Playwright/Edge và đặt `PLAYWRIGHT_MODULE` nếu module không ở node resolution mặc định; chạy `node scripts/evaluate_study_rhythm_ui.cjs` và `node scripts/evaluate_calendar_scroll.cjs`. Script dùng tài khoản/API fixture riêng, không thực hiện login/ghi dữ liệu lên tài khoản sinh viên thật.

## Giới hạn và phase tiếp theo

- Chỉ triển khai được cơ chế thử/quan sát; chưa có pilot, không tuyên bố cải thiện learning outcome hoặc tìm nhịp tập trung tối ưu.
- So sánh **trong cùng người**, đúng môn/task/activity/readiness/checkpoint. Deduplicate session; không trộn ca gốc vào ca sau. Đây là mô tả, task stage/difficulty vẫn có thể khác; không suy ra nhân quả.
- Chỉ hiển thị trial được xác nhận gần nhất, dựa trên tối đa60 timer session gần nhất. Lịch sử cũ hơn có thể không đủ baseline; cần cohort/pilot chuyên biệt để nghiên cứu dài hạn.
- Heartbeat không chứng minh sự chú ý; PDF không click không bị coi bỏ học. Backend đang hoạt động và workspace autosave thành công mới đảm bảo persistence.
- **Pilot cần làm với người thật:** giảng viên kiểm tra nhãn độc lập, nhiệm vụ tương đương, có application/transfer/delayed reassessment; đo completion, hint dependency, fatigue, retention và deadline feasibility. Hiệu chỉnh ngưỡng rồi mới cân nhắc tự đề xuất nhiều kiểu nhịp hơn.
- Không thêm LLM request để đoán số phút; không thêm dependency/agent mới; không mở rộng thành phần mềm giám sát học viên. Không dùng test fixture này làm bằng chứng tải1000 user.

Code chính: [activity context](../src/services/study_activity.py), [rhythm policy](../src/services/study_rhythm.py), [scheduler](../src/services/planning.py), [timer API](../src/api/study_sessions.py), [settings](../frontend/pacewise/src/components/domain/ActivityRhythmSettings.tsx), [proposal/comparison](../frontend/pacewise/src/components/domain/RhythmProposalCard.tsx).
