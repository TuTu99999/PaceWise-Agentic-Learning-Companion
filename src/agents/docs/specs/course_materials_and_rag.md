# Đặc tả Tính năng: Quản lý Tài liệu Môn học & RAG Hỏi đáp cho Giảng viên và Người học

## 1. Mục tiêu (Goals)
1. **Phía Giảng viên (`/#/instructor`)**:
   - Cho phép giáo viên tải lên tài liệu học tập đa định dạng: Word (`.doc`, `.docx`), PDF (`.pdf`), Slide trình chiếu (`.ppt`, `.pptx`), Text (`.txt`, `.md`).
   - Lưu trữ an toàn toàn bộ dữ liệu tài liệu trong cơ sở dữ liệu (`PaceWise PostgreSQL` - bảng `pacewise_course_materials`), bao gồm metadata và nội dung gốc để không bao giờ bị thất lạc.
   - Tự động bóc tách (parse) nội dung văn bản theo cấu trúc trang/đoạn/slide, tạo vector embeddings bằng FastEmbed và lập chỉ mục tức thời vào **Qdrant Vector Database** theo namespace môn học (`institution_id`, `course_id`).
   - Giao diện trực quan trên `InstructorOverviewPage` (hoặc tab Tài liệu môn học): tải file, quản lý danh sách tài liệu môn học, xem trạng thái lập chỉ mục (index status, số chunks, kích thước), nút xem trước nội dung trích xuất và nút xóa tài liệu (xóa cả trong CSDL và Qdrant).

2. **Phía Người học (`/#/learn`)**:
   - Học sinh khi vào trang Learn của môn học tương ứng sẽ được:
     - Xem danh sách tài liệu học tập của môn học hiện tại do giảng viên tải lên.
     - Hỏi đáp (Q&A) tương tác trực tiếp với tài liệu: câu hỏi được nhúng vector, truy vấn tương đồng Cosine trong Qdrant lọc đúng môn học (`course_id`), re-rank và trích dẫn chuẩn xác `[Tên tài liệu, Trang X, Đoạn Y]` hoặc `[Tên Slide, Slide X]`.
     - Nhận gợi ý các tài liệu hỗ trợ học tập (Recommended Materials) liên quan trực tiếp đến câu hỏi hoặc chủ đề môn học.
   - **Chỉ tiêu chất lượng**:
     - Tỷ lệ truy vấn thành công 100% khi tài liệu đã index.
     - Phân định rõ ràng ngữ cảnh: không truy xuất chéo sang môn khác.
     - Độ trễ (latency) thấp: tối ưu hóa pipeline RAG, trả kết quả tức thì.

## 2. Mô hình Dữ liệu (Database Schema)
Bảng mới: `pacewise_course_materials` trong `PaceWise PostgreSQL` (`:5433`):
- `id` (VARCHAR(64), Primary Key, UUID)
- `institution_id` (VARCHAR(128), Index)
- `course_id` (INTEGER, Index)
- `title` (VARCHAR(255))
- `module_name` (VARCHAR(128)) - Tuần/Chương học
- `file_name` (VARCHAR(255))
- `file_type` (VARCHAR(32)) - pdf, docx, doc, pptx, ppt, txt, md
- `file_size` (INTEGER)
- `content_bytes` (BYTEA) - Lưu trữ file nhị phân trong DB
- `extracted_text` (TEXT) - Văn bản bóc tách
- `chunk_count` (INTEGER, Default 0) - Số chunks được index trong Qdrant
- `uploaded_by` (INTEGER, Index) - user_id giảng viên
- `created_at` (TIMESTAMP WITH TIME ZONE)
- `updated_at` (TIMESTAMP WITH TIME ZONE)

## 3. Kiến trúc API (Backend Contracts)
1. `POST /api/v1/instructor/materials/upload`:
   - Quyền: `instructor`
   - Form-data: `file` (UploadFile), `course_id` (int), `title` (optional), `module_name` (optional)
   - Xử lý: Đọc file bytes -> Lưu vào DB -> Trích xuất text (PDF/DOCX/PPTX/TXT) -> Chunking -> FastEmbed -> Qdrant upsert.
   - Trả về: Thông tin tài liệu và số lượng chunks đã index.
2. `GET /api/v1/instructor/materials`:
   - Quyền: `instructor`
   - Query: `course_id`
   - Trả về: Danh sách tài liệu của môn học (id, title, file_name, file_type, file_size, chunk_count, created_at...).
3. `DELETE /api/v1/instructor/materials/{material_id}`:
   - Quyền: `instructor`
   - Xóa trong DB và xóa tất cả points liên quan trong Qdrant theo `material_id`.
4. `GET /api/v1/materials/course/{course_id}`:
   - Quyền: `student` hoặc `instructor`
   - Trả về: Danh sách tài liệu học tập của môn để hiển thị gợi ý học tập trên `/learn`.
5. `GET /api/v1/materials/{material_id}/preview`:
   - Trả về trích đoạn nội dung tài liệu để xem nhanh.

## 4. Tích hợp RAG Qdrant & Điều hướng Mục/Phần Tài liệu (Section-Level Navigation)
- Mỗi chunk đưa vào Qdrant chứa metadata mở rộng:
  - `material_id`: ID tài liệu trong PostgreSQL.
  - `course_id`: ID môn học để lọc isolation.
  - `institution_id`: ID trường.
  - `document_title`: Tên tài liệu.
  - `file_name`: Tên file gốc.
  - `section_title`: Tên mục, tiêu đề phần, chương hoặc tiêu đề slide (ví dụ: `Mục 2.1: Xử lý dữ liệu khuyết` hoặc `Slide 3: Tổng quan`).
  - `page`: Trang (PDF) hoặc Slide số (PPTX).
  - `paragraph`: Số thứ tự đoạn trong trang/mục.
  - `location_detail`: Mô tả vị trí rõ ràng (`Mục: [Tên mục] · Trang X, Đoạn Y`).
  - `download_url`: Đường dẫn tải file tài liệu trực tiếp từ CSDL (`/api/v1/materials/{material_id}/download`).
  - `citation`: `[Tiêu đề tài liệu, Mục ..., Trang/Slide X]`.
  - `content`: Nội dung đoạn text.
- Phản hồi RAG của Study Support Agent:
  - Trong câu trả lời của AI và phần danh sách trích nguồn (`source_refs`): chỉ ra rõ ràng kiến thức nằm ở **mục nào, phần nào trong file tài liệu học**.
  - Cung cấp link/nút trực tiếp để sinh viên mở hoặc tải ngay file tài liệu tương ứng từ CSDL về máy để đối chiếu.
- Qdrant query: sử dụng filter `institution_id` và `course_id` đảm bảo tốc độ cực nhanh (< 20ms) và chính xác tuyệt đối.


## 5. Quy tắc Ràng buộc
- Không can thiệp, không code trong folder `lms-simulator`.
- Đảm bảo tuân thủ đầy đủ cấu trúc docs/plans/specs/completed theo `RULE.md`.
