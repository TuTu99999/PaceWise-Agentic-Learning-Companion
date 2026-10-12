# Danh sách Task Hiện Tại (Tasks)

Dưới đây là các task đã được thực hiện và kiểm chứng thành công:

- [x] **TASK-01: Mô hình hóa CSDL & Dịch vụ Lưu trữ Tài liệu Môn học (`pacewise_course_materials`)**
  - Đã tạo bảng `pacewise_course_materials` trong PostgreSQL lưu trữ binary file bytes, metadata, extracted text và chunk count.
- [x] **TASK-02: Bộ bóc tách tài liệu chuẩn đa định dạng & Lập chỉ mục Vector tức thời vào Qdrant**
  - Đã xây dựng `src/services/material_service.py` hỗ trợ parse PDF, Word (.docx), PowerPoint (.pptx), Markdown/Text, tự động sinh FastEmbed embeddings và upsert vào Qdrant với namespace cô lập `course_id`.
- [x] **TASK-03: API Endpoints cho Giảng viên & Người học**
  - Đã xây dựng `src/api/materials.py` gồm các API upload, list, delete, preview, download cho cả giảng viên và sinh viên.
- [x] **TASK-04: Tích hợp Giao diện Quản lý Tài liệu trên trang Instructor (`/#/instructor`)**
  - Đã tích hợp `CourseMaterialsCard.tsx` vào `InstructorOverviewPage.tsx` với đầy đủ modal tải file, bảng hiển thị danh sách, xem trước và xóa.
- [x] **TASK-05: Tích hợp Giao diện Người học trên trang Learn (`/#/learn`) & Tối ưu Chất lượng Truy vấn RAG**
  - Đã bổ sung tab "Tài liệu môn học" và các chip gợi ý câu hỏi thông minh, cho phép học sinh hỏi đáp trực tiếp với tài liệu do giáo viên tải lên với độ trễ thấp và trích nguồn chuẩn xác.
- [x] **TASK-06: Chỉ mục Mục/Phần chi tiết (Section-Level RAG) & Liên kết tải/mở tài liệu trực tiếp từ CSDL trong Hỏi đáp**
  - Đã bóc tách tiêu đề mục/phần/chương/slide (`section_title`, `location_detail`).
  - Đã tích hợp API LLM từ proxy cấu hình trong `.env` (`Khanh-Combo`), thiết lập RAG Grounding nghiêm ngặt (chỉ trả lời trong phạm vi database tài liệu).
  - Tự động chỉ rõ tài liệu học mục nào phần nào trong file, kèm link tải trực tiếp từ CSDL PostgreSQL (`download_url`) và nút tải file ngay trên giao diện hỏi đáp của sinh viên.


