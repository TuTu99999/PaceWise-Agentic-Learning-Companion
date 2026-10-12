# Adaptive policy và evidence gates

## Scope

Trạng thái 2026-10-08: implementation và offline engineering acceptance đã pass
(354 backend tests, 119 frontend tests, 60 offline cases, typecheck/build/lint).
Live grading chưa nghiệm thu do provider timeout; task giữ ở trạng thái pending live validation,
không coi mock/synthetic pass là bằng chứng đánh giá hiểu bài đúng với learner thật.
Chi tiết: [validation](../../../../docs/adaptive-assessment-validation.md).

Bổ sung chuỗi checkpoint thích ứng trong Do, rubric criterion 0–4, hint ladder,
delayed reassessment và evidence gates. Không thêm phase/tab Assessment.

## Acceptance

- Item/rubric/KC phải lấy từ server; câu mới chỉ dùng item được duyệt.
- Policy chọn Recall → Explain → Why/How → Apply → Transfer; không đánh dấu
  mức chưa test là passed. Khi thiếu item được duyệt phải dừng và báo coverage gap.
- Hint được ghi nhận ở server; retry không tăng hint/attempt hoặc tạo evidence trùng.
- Trắc nghiệm đúng chỉ recognition; transfer cần reasoning/application và không hint.
- Retention chỉ được xác nhận khi tới hạn delayed probe, đúng course/KC, có baseline.
- Rubric 0–4 là criterion diagnostic, không ghi gradebook hay mastery probability.
- Test policy, adversarial gates, persistence/API và UI; ghi output thực tế.

## Files và verify

Services adaptive assessment/learning evidence, Do workflow, API và checkpoint UI.
Chạy pytest focused + backend suite, frontend typecheck/test/build và offline eval.
Chỉ chuyển task sang complete sau khi tất cả acceptance có bằng chứng.
