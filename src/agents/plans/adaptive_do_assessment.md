# Kế hoạch Adaptive Do Assessment

## Trạng thái

Các task 01–03 ở complete là **foundation checkpoint v1**, không phải bằng chứng toàn Phase 2 đã hoàn thiện.
Phần bổ sung adaptive policy đã hoàn thành ở mức engineering + live smoke tại [task 04](../complete/adaptive_do_assessment/task_04_adaptive_policy.md).
Luồng planning-signal tối giản đang được cập nhật tại [task 05](../task/adaptive_do_assessment/task_05_planning_signal_chat.md).
Nghiệm thu engineering và hạn chế live model được tổng hợp tại [evaluation evidence](../../../docs/evaluation-evidence.md).
Live smoke 2026-10-17 đạt 8/8 ca, 0 false-pass; vẫn không được diễn giải là learner validation.

1. **Truth contracts** — sửa closed evaluator theo item type; thêm evidence/event/snapshot schema và persistence idempotent.
2. **Do orchestration** — thêm action `assess` trong Do, tải assessment đã duyệt từ server, tạo assessment result/evidence, cập nhật Knowledge State có điều kiện.
3. **UX + Reflect loop** — checkpoint nằm trong phiên Do, theo dõi hint/first-attempt; clamp planning signal; nối output cho Plan nhưng không tự áp dụng.
4. **Evaluation** — unit/adversarial, persistence/idempotency, API integration, frontend workflow và offline eval report.

## Phụ thuộc

- Instructor assessment approval và LMS quiz metadata.
- Session/course authorization hiện có.
- PostgreSQL `create_all` cho bảng additive mới; production migration sẽ được tách khi deploy thật.

## Mốc nghiệm thu

- Closed adversarial cases không false accept.
- 100% evidence persisted có ID, KC, item/rubric/evaluator version, hint level và provenance.
- Retry cùng event key không tạo duplicate evidence/event.
- Thiếu evidence hoặc confidence thấp không nâng Knowledge State; hỏi kiểm chứng có giới hạn rồi giữ unknown, không tạo review từng câu trả lời.
- Assessment trong Do không sửa plan; Reflect signal luôn bounded.
- Backend/frontend/eval suite pass và giới hạn pilot được ghi rõ.
