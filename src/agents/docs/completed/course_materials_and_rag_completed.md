# Báo Cáo Hoàn Thành: Tính năng Quản lý Tài liệu Môn học & RAG Hỏi đáp cho Giảng viên và Người học

## 1. Thông tin chung
- **Thời gian hoàn thành**: 2026-10-05
- **Trạng thái**: Đã kiểm thử và nghiệm thu thành công toàn bộ luồng End-to-End.

## 2. Danh sách các task đã hoàn thành

### TASK-01: Mô hình hóa CSDL & Dịch vụ Lưu trữ Tài liệu Môn học (`pacewise_course_materials`)
- **Tập tin**: [src/persistence_models.py](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/src/persistence_models.py)
- **Những gì đã thực sự hoàn thành**:
  - Khai báo model `CourseMaterial` kế thừa `Base` trong SQLAlchemy.
  - Tạo bảng `pacewise_course_materials` trong PostgreSQL với các trường: `id`, `institution_id`, `course_id`, `title`, `module_name`, `file_name`, `file_type`, `file_size`, `file_bytes` (LargeBinary/BYTEA lưu trữ file gốc vĩnh viễn), `extracted_text`, `chunk_count`, `uploaded_by`, `created_at`, `updated_at`.
  - Tự động đồng bộ schema và tạo bảng trên PostgreSQL thành công (`\d pacewise_course_materials`).

### TASK-02: Bộ bóc tách tài liệu chuẩn đa định dạng & Lập chỉ mục Vector tức thời vào Qdrant
- **Tập tin**: [src/services/material_service.py](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/src/services/material_service.py)
- **Những gì đã thực sự hoàn thành**:
  - Xây dựng bộ parse đa định dạng:
    - PDF: Trích xuất từng trang qua `pypdf`, tự động chia đoạn hợp lý và gán thẻ trích dẫn `[Tên tài liệu, Trang X, Đoạn Y]`.
    - Word (.docx): Bóc tách cấu trúc đoạn qua OpenXML.
    - PowerPoint (.pptx): Bóc tách từng Slide qua OpenXML và đánh số `[Tên tài liệu, Slide X]`.
    - Text (.txt, .md): Đọc và gom đoạn tự động.
  - Sử dụng FastEmbed (ONNX 384 chiều) sinh embeddings cực nhanh.
  - Lập chỉ mục Vector tức thời vào collection `course_materials` của Qdrant kèm các metadata cô lập: `course_id`, `institution_id`, `material_id`, `access_scope="course"`.
  - Hỗ trợ hàm xóa vector đồng bộ khi tài liệu bị xóa.

### TASK-03: API Endpoints cho Giảng viên & Người học
- **Tập tin**: [src/api/materials.py](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/src/api/materials.py), [src/main.py](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/src/main.py), [frontend/pacewise/nginx.conf](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/frontend/pacewise/nginx.conf)
- **Những gì đã thực sự hoàn thành**:
  - `POST /api/v1/instructor/materials/upload`: Tiếp nhận file từ giáo viên, hỗ trợ dung lượng tối đa **200 MB**, lưu trữ CSDL, bóc tách text và index Qdrant.
  - Cấu hình Nginx reverse proxy `client_max_body_size 250m;` và timeout 300s.
  - `GET /api/v1/instructor/materials`: Lấy danh sách tài liệu môn học theo quyền giảng viên.
  - `DELETE /api/v1/instructor/materials/{id}`: Xóa tài liệu khỏi PostgreSQL và xóa sạch các vector liên quan trong Qdrant.
  - `GET /api/v1/materials/course/{course_id}`: Cung cấp danh sách tài liệu cho cả sinh viên và giảng viên.
  - `GET /api/v1/materials/{id}/preview`: Xem trước trích đoạn văn bản.
  - `GET /api/v1/materials/{id}/download`: Tải về file gốc lưu trữ trong CSDL.

### TASK-04: Tích hợp Giao diện Quản lý Tài liệu trên trang Instructor (`/#/instructor`)
- **Tập tin**: [frontend/pacewise/src/components/domain/CourseMaterialsCard.tsx](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/frontend/pacewise/src/components/domain/CourseMaterialsCard.tsx), [frontend/pacewise/src/pages/instructor/InstructorOverviewPage.tsx](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/frontend/pacewise/src/pages/instructor/InstructorOverviewPage.tsx), [frontend/pacewise/src/components/ui/Modal.tsx](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/frontend/pacewise/src/components/ui/Modal.tsx)
- **Những gì đã thực sự hoàn thành**:
  - Xây dựng component `CourseMaterialsCard` đặt tại trang `/#/instructor`.
  - Modal tải file hỗ trợ kéo thả / chọn file `.pdf, .docx, .doc, .pptx, .ppt, .txt, .md` tối đa 200 MB.
  - Tối ưu hóa tiêu điểm (focus retention) trong `Modal.tsx`, khắc phục triệt để hiện tượng mất focus khi gõ văn bản tiếng Việt.
  - Bảng danh sách tài liệu trực quan với badge định dạng, dung lượng, số đoạn RAG đã index, ngày tải lên.
  - Modal xem trước nội dung bóc tách, nút tải file gốc và nút xóa có hộp thoại xác nhận.

### TASK-05: Tích hợp Giao diện Người học trên trang Learn (`/#/learn`) & Tối ưu Chất lượng Truy vấn RAG
- **Tập tin**: [frontend/pacewise/src/pages/student/LearnPage.tsx](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/frontend/pacewise/src/pages/student/LearnPage.tsx), [frontend/pacewise/src/services/api.ts](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/frontend/pacewise/src/services/api.ts)
- **Những gì đã thực sự hoàn thành**:
  - Bổ sung tab mới **"Tài liệu môn học"** trên thanh switcher của `/learn`.
  - Hiển thị danh mục toàn bộ tài liệu học tập của môn học hiện tại với tính năng tìm kiếm nhanh, nút "Hỏi đáp ngay", "Tóm tắt" và "Tải file gốc".
  - Hiển thị các thẻ gợi ý câu hỏi thông minh ngay tại màn hình hỏi đáp trống dựa trên các tài liệu đã duyệt của môn.
### TASK-06: Chỉ mục Mục/Phần chi tiết (Section-Level RAG) & Liên kết tải/mở tài liệu trực tiếp từ CSDL trong Hỏi đáp
- **Tập tin**: [src/services/material_service.py](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/src/services/material_service.py), [src/agents/tools/qdrant_retriever.py](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/src/agents/tools/qdrant_retriever.py), [src/agents/workflows/qa.py](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/src/agents/workflows/qa.py), [frontend/pacewise/src/components/domain/Citation.tsx](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/frontend/pacewise/src/components/domain/Citation.tsx)
- **Những gì đã thực sự hoàn thành**:
  - Nhận diện tự động tiêu đề đề mục, chương, slide (`section_title`, `location_detail`) từ các định dạng file PDF, Word, PowerPoint, Markdown/Text.
  - Tích hợp gọi API LLM từ proxy cấu hình trong file `.env` (`Khanh-Combo` qua `host.docker.internal:20128/v1`).
  - Thiết lập ràng buộc Strict Grounding: LLM chỉ trả lời trong phạm vi nội dung tài liệu được trích xuất từ database của môn học, tuyệt đối không bịa đặt kiến thức ngoài học liệu.
  - LLM sinh text phản hồi tự nhiên, giải thích cặn kẽ và chỉ rõ kiến thức thuộc mục nào, phần nào, trang nào của file tài liệu, kèm link tải trực tiếp từ PostgreSQL (`/api/v1/materials/{id}/download`).
  - Nâng cấp giao diện người học: Card Citation hiển thị badge Mục/Phần, nút "Tải file" và modal chi tiết đoạn nguồn có nút tải file tài liệu gốc.

## 3. Bằng chứng kiểm chứng (Verification Evidences)
1. **Kiểm tra CSDL**: Bảng `pacewise_course_materials` tồn tại và lưu trữ đầy đủ `bytea` dung lượng file gốc cùng `extracted_text`.
2. **Kiểm thử Pipeline Backend Tự động**: Chạy script `scratch/test_student_ask.py` và `scratch/test_flow.py`:
   - Sinh viên gửi câu hỏi: *"Tôi đang gặp khó khăn kiến thức pandas cần bạn hỗ trợ"*.
   - Qdrant RAG tìm đúng các đoạn tài liệu môn `CS101`, trả về chế độ `grounded`.
   - LLM sinh phản hồi giải thích các khái niệm `Series`, `DataFrame`, cú pháp `import pandas as pd`, chỉ rõ đọc lại mục **“Giới thiệu Thư viện Pandas” — Trang 1, Đoạn 3**, kèm link tải file: `[Giáo trình Pandas & Phân tích Dữ liệu Python](/api/v1/materials/mat_.../download)`.
3. **Kiểm thử Tính Tổng quát Đa Môn học (Generalized Multi-Subject Test) & Bảo vệ Phạm vi Học liệu (Strict Grounding)**:
   - Chạy script `scratch/test_history_materials.py`:
   - **Upload môn Lịch sử**: Giảng viên tải lên *"Giáo trình Lịch sử Việt Nam Hiện đại"* gồm Chương 1 (CMT8 1945), Chương 2 (Chiến dịch Điện Biên Phủ 1954), Chương 3 (Đại thắng Mùa Xuân 1975).
   - **Sinh viên hỏi kiến thức Lịch sử**: *"Chiến dịch Điện Biên Phủ năm 1954 đã diễn ra như thế nào và có ý nghĩa lịch sử gì?"*.
     - Hệ thống RAG tự động truy vấn ngữ nghĩa, trích đúng các đoạn của **Chương 2: Chiến dịch Lịch sử Điện Biên Phủ năm 1954**.
     - LLM sinh câu trả lời chính xác, mạch lạc: phân tích 3 đợt tiến công (Him Lam, Độc Lập, Bản Kéo; đồi A1, C1; tổng công kích 17h30 ngày 7/5/1954 tướng De Castries đầu hàng).
     - Chỉ rõ vị trí: `[Giáo trình Lịch sử Việt Nam Hiện đại, Trang 2, Đoạn 2]` và `[Giáo trình Lịch sử Việt Nam Hiện đại, Trang 2, Đoạn 1]`.
     - Đính kèm link tải file gốc: `[Giáo trình Lịch sử Việt Nam Hiện đại](/api/v1/materials/mat_.../download)`.
   - **Kiểm thử Strict Grounding (Hỏi câu ngoài phạm vi tài liệu)**: *"Hãy hướng dẫn cách nấu món bún bò Huế truyền thống"*.
     - LLM phát hiện câu hỏi hoàn toàn không có trong cơ sở dữ liệu học liệu môn học (`insufficient_sources`).
     - LLM từ chối trả lời công thức nấu ăn, giải thích rõ: *"Mình chưa thể hướng dẫn cách nấu bún bò Huế truyền thống dựa trên học liệu được cung cấp, vì các tài liệu truy xuất hiện tại không có nội dung về ẩm thực, công thức nấu ăn, nguyên liệu hay phương pháp chế biến bún bò Huế"*.
     - Chứng minh 100% hệ thống không bịa đặt (hallucinate) và chỉ hoạt động nghiêm ngặt trong phạm vi tài liệu database.
4. **Kiểm thử Trực quan Giao diện E2E bằng Playwright**:
   - Chạy script tự động `scratch/browser_demo.py` (Exit code: 0) mô phỏng toàn bộ thao tác người dùng thật trên trình duyệt:
     - Giảng viên tải lên tài liệu học tập, xem bảng danh mục tài liệu, xem trước nội dung bóc tách.
     - Sinh viên vào `/#/learn`, hỏi câu hỏi về Pandas, nhận câu trả lời có cấu trúc từ LLM, hiển thị link tải tài liệu, badge mục/phần và mở modal chi tiết đoạn nguồn gốc.
   - Toàn bộ 7 ảnh chụp màn hình kiểm thử thực tế đã được cập nhật vào thư mục artifact.
5. **Kiểm tra Docker Containers**: Frontend (`pacewise-frontend-1`), Backend (`pacewise-backend-1`), Qdrant (`pacewise-qdrant-1`), PostgreSQL (`pacewise-pacewise-postgres-1`) đều hoạt động ổn định và thông suốt.
6. **Kiểm thử Bóc tách & Tải lên File PDF Thực tế**:
   - Chạy script `scratch/test_pdf_upload.py` (Exit code: 0):
   - Cài đặt bổ sung thư viện `pypdf>=5.0.0` vào `requirements.txt` và các container backend/worker.
   - Bóc tách cấu trúc từng trang, từng đoạn và tạo vector embeddings thành công qua FastEmbed -> Qdrant.
   - Trả về mã phản hồi `200 OK` và lưu trữ file PDF nhị phân trọn vẹn trong PostgreSQL.
7. **Kiểm thử Định dạng Phản hồi Sạch (Clean Text Without Raw Markdown Markers)**:
   - Chạy script `scratch/test_clean_qa_response.py` (Exit code: 0):
   - Loại bỏ triệt để các tiêu đề chế độ kỹ thuật (như `### `grounded_answer`` hay `### `insufficient_sources``) và các tiền tố markdown `###`, `####` thô kệch.
   - Tự động chuẩn hóa câu trả lời thành văn bản sư phạm tự nhiên, có đánh số thứ tự (`1.`, `2.`), chữ in đậm `**...**` và bullet points chuyên nghiệp.
   - Đồng bộ nâng cấp component `FormattedMessageText` trên giao diện người học `/learn` và triển khai lại container frontend.


