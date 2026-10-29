# Quy ước tài liệu và task cho coding agent

Với tính năng trong `src/agents`, dùng đúng bốn tầng:

- `src/agents/specs/*.md`: đặc tả hệ thống ngắn gọn, gồm mục tiêu, contract và quyết định.
- `src/agents/plans/*.md`: kế hoạch ngắn gọn, gồm thứ tự, phụ thuộc và mốc nghiệm thu.
- `src/agents/task/<feature>/*.md`: ít task được gộp theo đầu ra thực thi; mỗi task đủ rõ để code, test và tự nghiệm thu, có scope, contract, edge cases, file dự kiến và lệnh/bằng chứng kiểm chứng. Viết chi tiết nhưng không lan man hoặc chép lại specs.
- `src/agents/complete/<feature>/*.md`: chỉ chuyển task sang đây sau khi đạt acceptance criteria và ghi bằng chứng hoàn thành. Không giữ bản sao tại `task/`.

Khi cập nhật plan hoặc đổi tên task, sửa các liên kết liên quan. Không đánh dấu task hoàn thành khi mới viết kế hoạch.
