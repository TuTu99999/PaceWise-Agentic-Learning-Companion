# Reflect: sửa lỗi và bằng chứng kiểm thử — 08/10/2026

Scope vẫn là **Plan → Do → Reflect**. Reflect đọc kết quả Assessment trong Do;
không chấm lại kiến thức, không ghi mastery, không tự áp dụng lịch.

## Ba lỗi đã sửa

| Lỗi tái hiện trước đó | Hành vi sau sửa | Thành phần |
| --- | --- | --- |
| Model đổi planned_minutes từ 60 thành 999 | Evidence là bản sao input bất biến. Echo không khớp hoặc thêm fact lạ bị đánh dấu MODEL_EVIDENCE_CONFLICT; bỏ nhận xét và signal của response đó | reflect.py |
| Phiên trước missed nhưng phiên cuối completed khiến weekly giữ lịch | Xét mọi phiên ghi nhận đúng tuần, mọi môn thuộc enrollment. Ca này tạo propose_draft với missed_block | reflection_observations.py, replan_policy.py, agent_memory.py |
| missing_prerequisite bị Plan đổi thành none | Reflect, Plan adapter và policy dùng cùng contract. Alias legacy được map rõ; unknown giữ unrecognized_cause | planning_signals.py, plan_intelligence.py |

API tải số liệu từ memory/event/assessment records theo institution, student,
enrollment và tuần. Counter từ browser nằm trong self_report, không ghi đè số liệu
quan sát. Sai định dạng tuần trả 422 trước khi gọi model.

Nguồn timer/progress được ghi rõ **persisted_student_report**: việc lưu ở backend
không biến lời tự báo thành bằng chứng hiểu bài. Assessment giữ nguồn riêng.

## Weekly aggregation và stability

- Activity chỉ đọc block đã chọn trong môn đang xét, không mượn dữ kiện của block khác.
- Weekly đọc các course memories trong enrollment; khóa KC gồm cả course ID.
- STUDY_SESSION_COMPLETED được audit để phiên mới không biến mất khi memory rút gọn còn 20 phiên.
- Dedup theo course/block; retry giống nhau không nhân đôi phút hay session count.
- Ngày block trong server-confirmed plan được ưu tiên khi có; legacy dùng recorded_at.
- Evidence hợp lệ, confidence medium/high mới có thể tạo knowledge-gap trigger.
- Lấy quan sát mới nhất **cho từng chiều được kiểm tra**: pass Application mới có
  thể xử lý failure Application cũ; Recall mới không che failure Application.
- Chẩn đoán misconception confirmed chỉ được xóa bằng trạng thái resolved rõ ràng.
- Giữ fingerprint dedup và cooldown 30 phút; không tự áp dụng lịch.
- Confirmation weekly đọc lại observations từ database, không lấy số liệu LLM
  hoặc counter client để quyết định re-plan.

## Output thực tế của regression

| Case | Output đã kiểm chứng |
| --- | --- |
| Model evidence planned=999; input planned=60 | draft.evidence.planned_minutes=60; MODEL_EVIDENCE_CONFLICT |
| Model thêm fact không có trong input | Reject echo, giữ input, bỏ advice |
| Phiên đầu missed 60 phút, cuối completed 60 phút | propose_draft; missed_block; observed_session_count=2 |
| Confirm lại cùng bộ dữ kiện | keep; duplicate_signal; requires_confirmation=false |
| Application failed → Application passed, cùng KC/course | keep khi không có rủi ro khác |
| KC cùng tên nhưng khác course còn Application failed | propose_draft; nguồn evidence của course còn yếu |
| Sau failure chỉ kiểm tra Recall | Knowledge gap Application vẫn còn |
| Tất cả 15 cause contract qua Reflect → Plan | Không mất tên cause |
| Legacy underestimated / distraction | estimate_error / interruption |
| Cause lạ, NaN/Infinity, malformed affected_kcs | unknown + original cause; factor=1; follow_up=0; KCs=[] |
| Browser gửi planned=999, persisted session planned=60 | API đưa planned=60 cho agent; self_report.planned=999 |
| 22 phiên mới + retry | 22 phiên trong weekly, 22 completion audit events dù memory còn 20 |

Các output đầy đủ, không phải số liệu dự kiến:

- [Evaluator Reflect](../scripts/evaluate_reflect_safety.py)
- [18/18 ca Reflect + live smoke](../evals/reports/reflect-safety-2026-10-08.json)
- [400 backend tests](../evals/reports/reflect-fixes-backend-2026-10-08.xml)
- [125 frontend tests, 34 files](../evals/reports/reflect-fixes-frontend-2026-10-08.xml)
- [Adaptive engineering evaluation, 60/60 + legacy pass](../evals/reports/reflect-fixes-engineering-2026-10-08.json)

Frontend typecheck và lint code sửa pass. Không thay đổi UI trong lượt sửa này;
frontend tests xác nhận các hành vi đang có không bị hồi quy.

## Provider thật

Một case weekly tổng hợp qua 9router trên Windows:

- Process override OPENAI_BASE_URL=http://127.0.0.1:20128/v1.
- Model cx/gpt-5.6-sol; responded; 10.878 giây.
- status=awaiting_student.
- evidence_preserved=true; assessment_not_written=true.
- Model nêu đây là phản tư sớm, planned=120, actual=60, có một phiên missed;
  không kết luận hiểu bài khi chưa có Assessment.
- Signal interruption, factor=1, follow_up=60; vẫn cần student confirm.
- Không sửa .env, không viết dữ liệu LMS hay hồ sơ sinh viên thật.

Đây là **một smoke case**, không phải đánh giá có nhãn chuyên gia hay pilot.

## Chạy lại

PowerShell tại root repo:

    $env:DATABASE_URL='sqlite:///./tmp/reflect-fixes-20261008.db'
    .venv\Scripts\python.exe -m pytest tests -q
    .venv\Scripts\python.exe scripts/evaluate_reflect_safety.py

Live smoke nếu 9router đang chạy:

    $env:OPENAI_BASE_URL='http://127.0.0.1:20128/v1'
    .venv\Scripts\python.exe scripts/evaluate_reflect_safety.py --live-model

## Giới hạn còn lại

- Giữ evidence bất biến và reject echo sai **không chứng minh mọi câu văn tự do của
  LLM đều đúng**. Narrative interpretation vẫn cần kiểm tra; không dùng làm ground truth.
- Dữ liệu legacy đã mất khỏi 20-session memory trước khi có completion events không
  thể khôi phục tự động. Không có records được báo no_observations, không kết luận
  sinh viên không học.
- Phiên không mở Do và không có bản ghi completion chưa được suy đoán là missed.
  Ca regression missed là phiên đã ghi nhận. Không gán vắng mặt từ lịch lớp thành Do missed.
- Chưa có SME labels/pilot; chưa chứng minh retention, learning gain hoặc tăng on-time
  submission trong thực tế chỉ từ test pass.
- Chưa restart/rebuild container trong lượt này; tiến trình không hot-reload cần khởi động
  lại theo workflow phát triển của người dùng để sử dụng backend mới.

**Kết luận:** ba lỗi kỹ thuật R1/R2/R3 đã có bản sửa và regression pass.
Không dùng kết luận này để tuyên bố toàn bộ kiến trúc hay hiệu quả giáo dục đã hoàn thiện.
