# 4. Đặc tả và thiết kế

## Product specification

| Tài liệu | Mục đích |
|---|---|
| [Topic requirements](../../00-topic-requirements.md) | Yêu cầu bài toán ban đầu |
| [Product brief](../../01-brief.md) | Tầm nhìn, người dùng và giá trị |
| [PRD](../../02-prd.md) | Phạm vi, chức năng và tiêu chí thành công |
| [Project charter](../../04-project-charter.md) | Mục tiêu, phạm vi và cách thực hiện |
| [User stories](../../06-user-stories.md) | Hành vi theo vai trò |

## UX và interaction design

| Tài liệu | Mục đích |
|---|---|
| [Wireframe và UI flow](../../03-wireframe-uiflow.md) | Luồng màn hình chính |
| [Sitemap](../../ux/sitemap.md) | Cấu trúc thông tin |
| [User flows](../../ux/user-flows.md) | Luồng tác vụ người dùng |
| [Screen states](../../ux/screen-states.md) | Trạng thái giao diện |
| [Microcopy](../../ux/microcopy.md) | Quy tắc nội dung UI |
| [Acceptance criteria](../../ux/acceptance-criteria.md) | Điều kiện nghiệm thu UX |

## Technical và AI design

| Tài liệu | Mục đích |
|---|---|
| [Architecture](../../architecture_diagram.md) | Component, data flow và ownership |
| [AI workflows và evaluation](../../05-ai-workflows-and-evaluation.md) | Agent contracts và evaluation |
| [Course materials and RAG](../../specs/course_materials_and_rag.md) | Tài liệu môn học và retrieval |
| [Instructor role foundation](../../specs/instructor-role-foundation.md) | Quyền và workflow giảng viên |
| [Production configuration](../../production-configuration.md) | Cấu hình deploy an toàn |

## Quyết định thiết kế cốt lõi

- AI tạo bản nháp; sinh viên xem và xác nhận trước khi đổi lịch.
- Assignment tương lai vẫn xuất hiện trong Plan nhưng Do không được xếp/mở trước
  `earliest_start_at` của buổi học liên quan.
- Assessment dùng câu hỏi và ý cần đạt do giảng viên duyệt; kết quả là tín hiệu
  cho Plan, không phải điểm môn học.
- Khi bằng chứng chưa đủ hoặc confidence thấp, hệ thống hỏi thêm; không thay đổi
  kế hoạch lớn chỉ từ một câu trả lời yếu.
- RAG chỉ trả nguồn người dùng được phép xem; thiếu evidence thì nói rõ thiếu
  nguồn thay vì tạo citation.
