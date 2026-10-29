# Task 02 — Adaptive Assessment bên trong Do (hoàn thành)

## Đầu ra

- Do hỗ trợ action `assess`, gọi assessment engine nội bộ và vẫn trả workflow `do`.
- API chỉ tải assessment đã duyệt từ server, kiểm course/session và không tin rubric/answer từ client.
- Evidence được lưu trước khi derive Knowledge State; KC unmapped/confidence thấp/HITL không nâng state.
- Instructor có thể cấu hình answer type, cognitive level và approved KC mapping.
- Assessment không dispatch Plan/Recover hoặc tự đổi study block.

## Bằng chứng nghiệm thu

- Workflow/API integration tests xác minh approved server contract và persistence.
- Retry event được kiểm tra idempotent; cumulative snapshot giữ toàn bộ evidence IDs.
- Full backend: `303 passed`; Ruff pass.
