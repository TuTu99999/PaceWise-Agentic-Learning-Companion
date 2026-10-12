# Task 03 — Do checkpoint UI, Reflect signal và eval (hoàn thành)

> Hoàn thành nền tảng checkpoint v1, không phải toàn bộ Adaptive Assessment/Phase 2.
> Các con số bên dưới là kết quả lịch sử ngày 2026-10-07, không chứng minh chấm hiểu bài với sinh viên thật.
> Phần bổ sung và kết quả hiện tại: [adaptive validation](../../../../docs/adaptive-assessment-validation.md).

## Đầu ra

- Checkpoint, Socratic hint và feedback evidence nằm ngay trong Study Session; không thêm tab Assessment.
- Gửi first-attempt/hint level/event key tới backend và hiển thị trạng thái provisional/HITL.
- Reflect đọc Knowledge State, normalize cause và clamp duration factor `0.75–1.5`, follow-up `0–180`.
- Offline assessment truth/gate dataset độc lập với evaluator output được thêm vào release eval.

## Bằng chứng nghiệm thu

- Frontend: `114 passed`, typecheck pass, production build pass.
- Full backend: `303 passed`; Ruff pass.
- Eval `2026-10-07.v3`: 140 assessment cases, mọi release threshold pass.
- Giới hạn được công bố: offline fixtures chưa thay thế SME labels hoặc pilot sinh viên thật.

