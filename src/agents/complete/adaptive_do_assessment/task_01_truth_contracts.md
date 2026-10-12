# Task 01 — Truth contracts và evidence store (hoàn thành)

## Đầu ra

- Closed evaluator typed cho MCQ, boolean, numeric và exact text; không còn false accept theo ký tự đầu.
- Thêm LearningEvidence, LearningEvent, KnowledgeStateSnapshot có schema/evaluator version và provenance.
- Persistence idempotent theo event key; snapshot tích lũy source evidence nhưng không sửa lịch sử.
- Thiếu bằng chứng/provenance trả `insufficient_evidence`; closed answer đúng chỉ chứng minh recognition.

## Bằng chứng nghiệm thu

- `tests/test_agents/test_rubric_evaluator.py`
- `tests/test_services/test_learning_evidence.py`
- Full backend: `303 passed`.
- Assessment offline eval: closed accuracy `1.0`, false mastery acceptance `0.0`.

