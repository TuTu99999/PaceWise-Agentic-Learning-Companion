# LMS-owned materials — implementation and evaluation

Ngày kiểm thử: 09/10/2026. Scope sản phẩm vẫn **Plan → Do → Reflect**.

## Phạm vi đã thay đổi

LMS simulator quản lý upload, phiên bản mới, quyền toàn môn hoặc từng sinh viên, và xóa file. PaceWise không còn tab **Nội dung & học liệu** hay **Cấu trúc môn học/nạp data**; đường dẫn cũ redirect về Tổng quan lớp. Không xóa dữ liệu KC/rubric hoặc tài liệu cũ của người dùng.

PaceWise giữ bản dẫn xuất trong bảng `lms_file_indexes`: metadata, fingerprint, text/chunks, trạng thái và lỗi xử lý. Binary gốc không được lưu thêm. PDF xem qua proxy có session, kiểm tra enrollment/ACL/checksum và trả `Cache-Control: private, no-store`.

```text
LMS upload / replace / delete / access change
→ integration event + reconciliation 60s
→ bounded authenticated download (20 MB, không theo redirect / URL ngoài)
→ checksum + format validation
→ extraction / chunks (PDF theo trang, PPTX theo slide)
→ durable pending/retry → Qdrant
→ live per-user manifest → course/file/version filter → chatbot có citation
```

Do chọn tài liệu được quyền truy cập và mở tab mới qua proxy. Chat không embedding trong request. File chưa index hoặc không còn phiên bản hợp lệ không được dùng làm bằng chứng trả lời. File PDF scan không có text được báo lỗi, không coi binary là nội dung học.

## Kiểm thử đã thực hiện

- Backend: **411 passed**, JUnit: [backend](../evals/reports/lms-materials-backend-2026-10-09.xml).
- Frontend: **159 passed**, JUnit: [frontend](../evals/reports/lms-materials-frontend-2026-10-09.xml).
- LMS simulator: **14 passed**, JUnit: [simulator](../evals/reports/lms-materials-simulator-2026-10-09.xml).
- Production frontend build và TypeScript: PASS. Entry bundle khoảng **342.78 kB**, gzip **108.67 kB**; không có cảnh báo chunk trên 500 kB.
- Lint Python các phần sửa, `node --check lms-simulator/static/app.js`, `git diff --check`: PASS.

Đây là **test tự động**, không ghi giả thành manual test. Test tích hợp dùng HTTP ASGI của LMS simulator thật, SQLite cô lập, parser PDF thật và Qdrant in-memory thật. Embeddings trong test là vector xác định; không phải benchmark semantic retrieval hoặc LLM production.

### Các ca quan trọng và output đã kiểm tra

| Ca | Output/assertion thực tế | Kết quả |
|---|---|---|
| Upload PDF ở LMS | HTTP 200; parser thu được `A relation is a subset of A cross B.`; nguồn `page=1`; URL `/api/v1/lms-files/77/…/download` | PASS |
| Sync file không đổi | Worker không tạo việc index mới; số lời gọi embedding không tăng | PASS |
| Idempotency qua restart | Bỏ process cache vẫn trả `unchanged`; xóa rồi nạp lại cùng nội dung tạo vector lại | PASS |
| Thu hồi quyền trước khi worker cleanup | Manifest sinh viên rỗng; retrieval rỗng; download/version history HTTP 403 | PASS |
| Cấp quyền cho một sinh viên | Sinh viên 2 có file; sinh viên 3 không thấy file; replace vẫn giữ ACL | PASS |
| Thay PDF | Phiên bản 2; trước khi index mới retrieval abstain; sau index chỉ nội dung mới `A symmetric relation reverses every pair.` | PASS |
| Xóa file ở LMS | HTTP 200; manifest rỗng ngay; worker xóa vector của file | PASS |
| Events lifecycle | Có `resource.created`, `resource.updated`, `resource.access.updated`, `resource.deleted` | PASS |
| PDF proxy | HTTP 200, `%PDF`, MIME `application/pdf`, `private, no-store`; khác môn hoặc đã thu hồi: 403 | PASS |
| Spoof teacher bằng student | Upload với `user_id` giảng viên nhưng session sinh viên: 403 | PASS |
| URL ngoài / thiếu service key | Không fetch URL metadata AWS; download URL ngoài 422; thiếu key 401/403 | PASS |
| Checksum sai, PDF/DOCX/PPTX hỏng | Không lưu chunks khả dụng; trạng thái lỗi hoặc validation exception | PASS |
| LMS manifest lỗi | Không coi lỗi mạng như manifest rỗng để xóa nguồn | PASS |
| Cleanup nội dung text | Không xóa vector `source_type=lms_file` | PASS |
| Teacher navigation | Hai tab quản lý cũ không còn; URL cũ redirect; không preload/bundle trang cũ | PASS |
| Status UI và đổi môn | Hiện trạng thái/index count; lỗi tải có thông báo; response môn trước không ghi đè môn mới | PASS |
| Upload PaceWise cũ | HTTP 410 mặc định; đọc tài liệu legacy vẫn giữ | PASS |

Test lifecycle: [test_lms_file_integration.py](../tests/test_services/test_lms_file_integration.py).

## Đánh giá và giới hạn

**Đã kiểm chứng luồng kỹ thuật với LMS simulator của repo**, gồm lifecycle file, dẫn xuất, index, nguồn Do, proxy và quyền trước retrieval. Không tuyên bố đã tích hợp Canvas production thật.

Còn cần trước khi đưa vào trường:

1. Adapter Canvas Files/Modules thực, OAuth hoặc LTI và token/user-scoped permissions theo cấu hình trường. Không dùng service token quyền giảng viên để suy ra quyền sinh viên.
2. Kiểm thử sandbox Canvas: locked/unpublished/unlock date, section/group/user visibility, pagination, rate limit, deleted files và URL download hết hạn.
3. Kiểm thử browser bằng người dùng thật, mobile PDF viewer và tải đồng thời; bài này chỉ xác nhận UI bằng React tests và build, chưa kiểm tra thao tác trên trình duyệt thật.
4. Đánh giá retrieval/citation với embeddings/LLM thật trên học liệu tiếng Việt; test vector xác định không chứng minh chất lượng câu trả lời.
5. OCR cho PDF scan; chạy extraction trong worker cô lập tài nguyên nếu tiếp nhận tài liệu ngoài môi trường demo.

Thu hồi không thể lấy lại nội dung sinh viên đã xem/tải trước đó hoặc xóa kiến thức đã gửi tới LLM trước thời điểm thu hồi. Cơ chế ở đây chặn **request truy cập mới**, không phải DRM.

## Chạy bản mới

```powershell
docker compose up -d --build lms-simulator backend worker frontend
```

Không dùng `down -v`: cần giữ dữ liệu hiện có. Vào LMS → môn → Files để upload. Trên PaceWise → Tổng quan lớp xem trạng thái; trên Do mở nguồn PDF. Worker tạo bảng dẫn xuất mới khi khởi động qua `initialize_database()`.

`ALLOW_LEGACY_MATERIAL_WRITES=false` mặc định. Chỉ bật tạm nếu có kế hoạch migration tài liệu cũ; UI upload PaceWise không được khôi phục theo flag này. Không tự động chuyển/xóa binary cũ của người dùng trong thay đổi này.
