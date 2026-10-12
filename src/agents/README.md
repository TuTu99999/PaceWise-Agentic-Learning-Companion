# Quy ước tài liệu và vòng đời task

Mọi tính năng trong `src/agents` tuân theo cấu trúc sau:

```text
src/agents/
├── specs/       # Đặc tả hệ thống và thiết kế đã thống nhất
├── plans/       # Kế hoạch triển khai
├── task/        # Mỗi task chưa hoàn thành là một file Markdown riêng
└── complete/    # Task đã hoàn thành, được chuyển từ task/ sang
```

## Quy tắc

1. Không đặt đặc tả hệ thống hoặc kế hoạch triển khai trong `docs/` hoặc `tasks/`.
2. Mỗi tính năng có cùng slug thư mục/file xuyên suốt bốn tầng.
3. `specs/*.md` và `plans/*.md` viết ngắn gọn: quyết định, contract và thứ tự triển khai; không chép lại checklist code.
4. Gộp các bước liên quan thành ít task có đầu ra kiểm chứng được. Không chia task chỉ vì khác file hoặc khác công cụ.
5. Mỗi task phải đủ chi tiết để coding agent thực hiện: bối cảnh cần đọc, phạm vi, contract, file dự kiến, lỗi/edge case, acceptance criteria và bằng chứng test. Dài vừa đủ, không lặp lại specs/plan.
6. Task chỉ tồn tại tại một vị trí: `task/` khi chưa xong hoặc `complete/` khi đã xong.
7. Chỉ chuyển task sang `complete/` sau khi đạt acceptance criteria và ghi bằng chứng hoàn thành.
8. Kế hoạch phải liên kết tới đặc tả và các task; task phải liên kết ngược về kế hoạch và đặc tả.

Ví dụ Teach-back:

```text
specs/teach-back.md
plans/teach-back-implementation.md
task/teach-back/TB-01-foundation.md
complete/teach-back/TB-01-foundation.md
```
