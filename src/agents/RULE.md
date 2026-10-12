# Quy tắc Quản lý Dự án & Task

Mỗi khi bắt đầu một dự án hoặc xử lý task mới, phải tuân thủ nghiêm ngặt cấu trúc tài liệu và quy trình dưới đây.

## 1. Cấu trúc thư mục bắt buộc
Dự án phải luôn có thư mục `docs` với cấu trúc sau:

```text
docs/
├── specs/          # Chứa các file .md đặc tả yêu cầu và chi tiết tính năng.
├── plans/          # Chứa kế hoạch và danh sách công việc.
│   ├── backlog.md  # Danh sách các task dự trữ, chưa cần làm ngay.
│   └── tasks.md    # Danh sách các task cần hoàn thành hiện tại.
└── completed/      # Chứa các file .md ghi lại thông tin các task đã xử lý xong.
```

## 2. Quy trình làm việc
- **Khi có task mới:** Phải ghi nhận ngay vào `docs/plans/tasks.md` hoặc `docs/plans/backlog.md`. Không làm việc nếu chưa có task được ghi ra.
- **Khi làm việc:** Tham khảo tài liệu tại `docs/specs/` để nắm rõ yêu cầu.
- **Khi hoàn thành task:** 
  - Gạch bỏ/Xóa task bên mục `plans`.
  - Tạo hoặc cập nhật file `.md` trong thư mục `docs/completed/`.
  - **Bắt buộc ghi rõ:** Tên task đã làm và danh sách chi tiết những gì đã thực sự hoàn thành. 


- Ko code ở folder: llms-simulator