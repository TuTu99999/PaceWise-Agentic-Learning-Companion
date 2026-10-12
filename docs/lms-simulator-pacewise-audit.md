# LMS simulator → PaceWise: audit và evaluation

Ngày: 09/10/2026. Phạm vi: hợp đồng dữ liệu và chức năng LMS cần cho **Plan → Do → Reflect**, không triển khai một bản sao đầy đủ của Canvas.

## 1. Kết luận

Simulator có nền tảng cần thiết, nhưng trước audit còn lỗi về publication/quyền, quiz không trở thành nhiệm vụ Plan, deadline riêng bị cache/planner note che mất, trạng thái bài đã chấm chưa được coi là hoàn thành trên UI, và một số thay đổi LMS không làm mới projection.

Các lỗi này đã được sửa và có regression. Giảng viên quản lý nguồn trên LMS; PaceWise nhận dữ liệu, lập kế hoạch và hỗ trợ học. Điểm quiz/rubric LMS **không tự chứng minh conceptual/application/transfer mastery**.

## 2. Ma trận chức năng đã rà

| Nhóm | PaceWise cần để làm gì | Kết quả / thay đổi |
|---|---|---|
| Login, enrollment, launch | Đúng SV, đúng môn, đúng role | Service key; kiểm tra enrollment ở view scoped; môn chưa publish không hiện cho SV; launch một lần, kiểm tra enrollment/role khi consume |
| Assignment CRUD | Mục tiêu, nội dung, hạn nộp | Có sẵn; chặn nộp assignment chưa publish; kiểm tra điểm không âm/non-finite |
| Quiz / kiểm tra | Nhiệm vụ ôn/làm quiz trong Plan và evidence trong Do | Thêm `QuizAssignmentLink`; quiz có deadline tạo assignment `online_quiz`; sửa title/deadline đồng bộ; xóa quiz unpublish assignment, giữ lịch sử submission |
| Quiz questions / attempts | Làm bài và kết quả thật | SV không đọc answer key; chặn quiz chưa publish/rỗng/locked, question ID lạ; tổng điểm assignment theo câu hỏi; nộp quiz tạo submission graded và attempt history |
| Deadline / availability | Không xếp sau hạn hoặc trước mở bài | Scope theo SV; collapse từng trường của override; giữ giờ/phút; chuẩn hóa offset về UTC trước persist, kể cả SQLite |
| Student / section / group overrides | Hạn riêng theo người/nhóm | Student override ưu tiên; khi không có thì due/lock lấy max, unlock lấy min của trường applicable; không trả danh sách override của người khác cho SV |
| Assignment groups / weight | Ưu tiên, không nhầm điểm với độ hiểu | Có sẵn; truyền group weight, points và grading metadata; policy/group changes làm mới assignment projection |
| Syllabus / pages / outcomes | Nguồn phân rã task, tài liệu và competency | Có sẵn; lọc publication trong view SV; không tự coi outcome point là bằng chứng hiểu bài |
| Rubric / feedback / grading | Tiêu chí, feedback cho Do/Reflect | Có sẵn; sửa API grades truyền sai tham số; kiểm tra enrollment người nhận điểm; rubric assessment tới được service payload; rating không vượt criterion points |
| Submissions / workflow | Phân biệt cần làm, đã nộp, miễn, làm lại | Chuẩn hóa submitted/graded/pending_review/excused/reassigned; giữ source state; UI graded → done, reassigned → todo; miễn bài không bị nhắc như chưa nộp |
| Planner notes | Ghi chú của SV, không thay dữ kiện LMS | Linked note lấy deadline và completion thật từ assignment/submission; không lấy `completed=true` do SV nhập làm submission; kiểm tra course/assignment khi tạo và sửa |
| Modules / requirements | Thứ tự và điều kiện học | Chặn prerequisite cycle; chặn started khi prerequisite chưa đạt; graded submission đạt requirement; quiz item resolve đúng assignment ID |
| Module item editor | Nối tài liệu/bài thật thay vì chỉ tên | Bổ sung select nội dung theo type, `content_id`, auto-fill tên; backend kiểm tra type/course/target; view SV không lộ target chưa publish hoặc file mất quyền |
| Lịch dạy / cá nhân | Ràng buộc thời gian của Plan | SV không sửa ca dạy LMS; sửa lỗi nhầm event ID với user ID; validate khoảng thời gian; event create/update/delete có log |
| Sửa/xóa ca dạy ở LMS | Đổi lịch giảng viên phải đến được SV | Giảng viên sửa/xóa một occurrence class_session; cập nhật các calendar copies của ca đó; `TeachingEventLink` tách các ca trùng tên/giờ; PaceWise lịch dạy vẫn read-only |
| Appointment / office hours | Một khoảng bận thật, không lộ người khác | Validate window/slot, không đặt trùng group; row lock cho capacity PostgreSQL; view SV chỉ trả reservation của mình; reservation xuất hiện trong fixed calendar |
| Files / ACL / phiên bản | Nguồn Do/RAG được phép truy cập | Đã có upload/replace/revoke/delete/index từ lượt trước; regression tiếp tục chạy; module reference cũng phải qua file ACL |
| Worker / event projection | Đổi rubric/deadline/module không giữ cache cũ | Bổ sung event policy/override/group/rubric/module/activity/workflow; giữ audit event; agent context SV lấy scoped data live, không đọc/ghi chung teacher projection |
| Demo submission time | Demo nộp sớm/trễ mà không nhầm dữ liệu thật | Offset chỉ bật khi `ALLOW_DEMO_SUBMISSION_TIMING=true`; mặc định code false; Compose local demo true; UI ẩn nút mô phỏng khi tắt |

Weight ở đây là **weight của assignment group**, không phải một tỷ lệ đóng góp điểm riêng của từng bài. Simulator chưa cung cấp một phép tính đóng góp cá nhân hoàn chỉnh có xét drop rules/điểm chưa chấm; không dùng weight này như phép đo hiểu bài.

## 3. Đối chiếu Canvas local

Clone tham chiếu: `canvas-lms`, commit `1c9f0bb8`. Không sửa clone, không chạy test Ruby của Canvas, không bê code Ruby vào simulator Python.

- [Quiz.build_assignment](../canvas-lms/app/models/quizzes/quiz.rb): khoảng dòng 238, graded quiz liên kết assignment `online_quiz`, publication theo quiz. Áp dụng ý nghĩa linkage, không tuyên bố hỗ trợ mọi loại Canvas quiz/survey.
- [AssignmentOverrideApplicator](../canvas-lms/lib/assignment_override_applicator.rb): khoảng dòng 399–495, collapse từng trường và ưu tiên adhoc student override. Simulator áp dụng phần date có giá trị; **chưa có explicit overridden-null flags** của Canvas.
- [Quiz API serialization/policies](../canvas-lms/lib/api/v1/quiz.rb): các policy show/hide correct answers. Simulator dùng chính sách an toàn đơn giản: student service view không nhận answer key.

Đây là link tới clone local; clone có thể không nằm trong bản GitHub checkout. Đây không phải kiểm chứng native Canvas production API.

## 4. Bằng chứng kiểm thử

Các suite chạy trên DB test riêng/in-memory, không reset dữ liệu demo:

| Suite | Kết quả | Bằng chứng |
|---|---|---|
| LMS simulator | 62 passed | [JUnit](../evals/reports/lms-audit-simulator-2026-10-09.xml) |
| PaceWise backend | 432 passed | [JUnit](../evals/reports/lms-audit-backend-2026-10-09.xml) |
| Frontend, gồm DOM module editor simulator | 162 passed | [JUnit](../evals/reports/lms-audit-frontend-2026-10-09.xml) |
| Frontend production build | Passed; main JS ~342.78 kB, gzip ~108.66 kB | `npm run build` |
| Lint / syntax | Ruff passed, `node --check` passed | Các file Python liên quan và simulator `static/app.js` |

LMS baseline trước audit có 14 test; thêm 48 test LMS. Backend thêm 21 test, frontend thêm 3 test DOM. Đây là technical evaluation, **không phải 62 manual test trên browser**.

### Output thực tế đã được các test kiểm tra

| Case | Output / hành vi quan sát |
|---|---|
| Student gọi service course không enrolled | `403` trên assignments/submissions/modules/content/grades/quizzes/outcomes/appointment-groups |
| Assignment/module draft | SV thấy 1 published item; instructor thấy cả 2 published + draft |
| Planner note ghi deadline 2099 và `completed=true` | Vẫn trả title/đúng deadline LMS; `completed=false` khi chưa có submission |
| Deadline `12:17+07:00` | Persist/service tương ứng `05:17 UTC`, không mất 7 giờ; kiểm tra quiz, assignment, override |
| Override riêng trong real HTTP integration | SV A nhận `06:17 UTC`, SV B vẫn nhận `05:17 UTC`; không lấy planner note `31/12` |
| Plan chỉ rảnh buổi chiều sau deadline trên | `blocks=[]`, `qualityEvaluation.canConfirm=false` |
| Quiz 1 câu 2 điểm, chọn đúng | `score=2`, canonical submission `graded`; PaceWise task `done`; **không kết luận conceptual mastery** |
| Quiz bị xóa | Không còn trong student assignments; assignment lịch sử/submission được giữ |
| Grading service | `200`, current score `8`; rubric criterion score `8` tới cả summary/full payload |
| Module prerequisite/cycle | Cycle `422`; started khi thiếu prerequisite `409`; graded/quiz submission đạt score requirement cho phép completed |
| File mất quyền nhưng có module item | Không còn item trong student module view; không bypass qua module |
| Student sửa/xóa ca dạy | `403`, thông báo yêu cầu giảng viên thay đổi nguồn LMS |
| Teacher đổi ca có 2 người, 2 lần lặp | `affected_calendar_events=2`; SV nhận giờ mới `09:17–10:03`, 46 phút; tuần sau giữ nguyên |
| Hai ca mới trùng tên và giờ | Chỉ sửa/xóa occurrence được chọn, không gộp nhầm; legacy ambiguous trả `409`, giữ dữ liệu |
| Đặt office hours lệch slot / trùng group | `422` / `409`; reservation thật vào fixed calendar, không hiện user khác |
| Launch replay / enrollment bị thu hồi | `401` / `403` |
| Timing simulation khi tắt demo | `422`; không cho client tự chọn thời điểm nộp sớm/trễ |

Regression chính: [simulator contracts](../lms-simulator/tests/test_pacewise_contracts.py), [HTTP cross-system test](../tests/test_services/test_lms_file_integration.py), [consumer contracts](../tests/test_api/test_lms_integration_extended.py), [projection events](../tests/test_services/test_sync_worker.py), [DOM editor](../frontend/pacewise/tests/lms-module-editor.test.ts).

PDF/ACL/index evidence được giữ trong [materials evaluation](lms-materials-sync-evaluation.md). Embeddings trong integration test là vector deterministic; không dùng chúng để tuyên bố chất lượng semantic retrieval/LLM.

## 5. Giới hạn còn lại, không nên báo “Canvas production-ready”

1. API `/api/pacewise/v1` là contract riêng của simulator; native Canvas `/api/v1`, OAuth/LTI 1.3, pagination/rate limit và webhook production vẫn cần adapter + sandbox thật.
2. Assignment schema cần deadline: quiz không có due date không trở thành deadline task của Plan. Không tự gán hạn giả. Cần thiết kế backlog/no-deadline task nếu mở rộng.
3. Override explicit clear-to-null, only-visible-to-overrides, grading periods và toàn bộ Canvas date policy chưa đầy đủ.
4. Quiz hiện chủ yếu closed question, scoring đơn giản; chưa clone New Quizzes, question bank/randomization, essay/manual/partial scoring hay toàn bộ attempt/answer-release policies.
5. Ca dạy chỉnh theo **một occurrence class_session**; chưa có bulk “cả chuỗi/tất cả các buổi tương lai”. Lịch thi/video khác loại không chỉnh qua calendar cá nhân; cần quản lý lịch hoạt động nguồn tương ứng nếu mở rộng. Legacy trùng lặp không có occurrence ID bị chặn thay vì sửa đoán.
6. Appointment capacity có PostgreSQL row lock, nhưng chưa chạy load test concurrent trên PostgreSQL thật; cancellation/reschedule workflow đầy đủ chưa triển khai.
7. Có HTTP/DB/DOM test, nhưng chưa chạy manual browser toàn bộ UI LMS/production Docker sau audit. Không tuyên bố đã kiểm tra mọi layout hoặc mọi trạng thái nhập liệu bằng mắt.
8. Chưa chạy lại provider thật/SME grading/pilot SV trong audit này. Thời gian học, điểm LMS và synthetic fixtures không chứng minh learning outcome.

Ưu tiên tiếp theo: native Canvas adapter + sandbox contract test; workload/cancellation/concurrency tests; rồi pilot/calibration kiến thức. Không cần thêm tính năng account/inbox/chat/course-admin trùng Canvas để phục vụ Plan–Do–Reflect.

## 6. Áp dụng và chạy lại

Hai bảng mới `quiz_assignment_links`, `teaching_event_links` được tạo lúc startup. Startup link quiz có deadline với assignment tương ứng, không reset DB. Không xóa volume.

```powershell
docker compose up -d --build lms-simulator backend worker frontend
```

Trong LMS demo: **Content/Quizzes** tạo quiz/câu hỏi; **Modules → + Item** chọn nội dung có sẵn; **Calendar** giảng viên sửa ca dạy của mình, SV chỉ xem; **Files** quản lý nguồn cho Do.

Compose local bật mô phỏng nộp bài. Để test production-like, đặt `ALLOW_DEMO_SUBMISSION_TIMING=false` trước rebuild; không dùng số liệu mô phỏng làm KPI thật.

Chạy suite LMS từ repo root:

```powershell
$env:PYTHONPATH = 'lms-simulator'
$env:DATABASE_URL = 'sqlite:///./data/lms-audit-test.db'
.venv/Scripts/python.exe -m pytest lms-simulator/tests -q
```

Chạy backend ở shell mới hoặc bỏ `PYTHONPATH` ở trên; sử dụng DB test riêng. Frontend: `cd frontend/pacewise`, `npm test`, `npm run build`.
