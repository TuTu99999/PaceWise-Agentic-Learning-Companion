# Adaptive Question Design — triển khai và đánh giá

Ngày kiểm tra: 2026-10-09. Scope sản phẩm vẫn là **Plan → Do → Reflect**; Assessment nằm trong Do.

## 1. Thay đổi đã triển khai

Tab giảng viên **Ngân hàng câu hỏi** đổi thành **Thiết kế kiểm chứng**. Giảng viên sửa một câu mẫu đã có trong LMS và duyệt cấu hình dùng chung:

- KC được map, rubric, nguồn tham chiếu và phiên bản.
- `fixed`: dùng câu mẫu đã duyệt như trước.
- `relation_template`: sinh dữ kiện quan hệ hai ngôi bằng code, kiểm tra đáp án bằng oracle.
- `llm_followup`: hỏi tiếp nối theo câu trả lời vừa có và đoạn tham chiếu giảng viên xác nhận; chỉ formative.

Editor có preview các biến thể và đáp án checker dành riêng cho giảng viên. Preview không ghi câu vào ngân hàng. Đổi tính chất/rubric/nguồn thì preview cũ không còn hiển thị.

Luồng runtime:

```text
Câu mẫu + khung đã duyệt trong môn học
→ chọn KC và mức đang kiểm tra
→ sinh biến thể có checker / hỏi tiếp nối formative / fallback câu đã duyệt
→ lưu câu đã hiển thị trong phiên + audit
→ nhận câu trả lời
→ evidence hợp lệ mới được cập nhật Knowledge State
→ Assessment chọn mức/câu tiếp theo trong Do
→ Reflect đọc kết quả; Plan không bị chặn bởi hàng chờ duyệt
```

## 2. Đúng phạm vi triển khai

Khung đang gắn vào `InstructorAction` assessment có phiên bản và câu quiz LMS đã được duyệt, **chưa phải một dịch vụ tự đọc toàn bộ PDF rồi tự xuất bản blueprint**. Không thêm bảng ngân hàng chứa mọi biến thể LLM.

Template hiện hỗ trợ sáu tính chất của quan hệ hai ngôi: phản xạ, đối xứng, phản đối xứng, bắc cầu, tương đương, thứ tự bộ phận. Một khung template có thể phủ Recall → Explain → Why → Application → Transfer.

Oracle kiểm tra dữ kiện hữu hạn, tính chất, đáp án nhận biết và các cặp cần bổ sung. Bài chuyển giao thứ tự được sinh từ quan hệ không chu trình để phép bổ sung vẫn khả thi. Bài chuyển giao phản đối xứng hỏi thêm cặp làm mất tính chất thay vì yêu cầu sửa bằng phép thêm không thể thực hiện.

**Oracle không tự chấm được toàn bộ lập luận tự do.** Các câu mở vẫn dùng evaluator theo rubric và chính sách evidence/review đã có. Đây không phải bằng chứng rằng LLM chấm đúng mọi sinh viên.

## 3. Chính sách an toàn và tài nguyên

- Tối đa **16 instance generated** trong state của mỗi checkpoint; không lưu candidate bị bỏ qua.
- Tối đa **2 lần gọi LLM generator** mỗi checkpoint; mỗi lần cấu hình HTTP timeout 8 giây, 0 retry, 350 output tokens.
- Đây là timeout của request, không phải SLA tuyệt đối cho toàn endpoint gồm LMS, DB và grader. Grader giữ cấu hình riêng.
- Đoạn tham chiếu tối đa 5.000 ký tự; câu trả lời trước gửi generator tối đa 1.500 ký tự; câu generated được chấp nhận dài 15–800 ký tự.
- Reference dùng chung không bị sao chép vào mỗi instance.
- Câu đã hỏi lưu snapshot, source, stage, parent/version, engine version trong audit; câu đã trả lời có evidence/provenance riêng. Không lưu đáp án private vào response checkpoint.
- Reload tiếp tục câu hiện tại, không sinh lại. Parent bị thu hồi duyệt/xóa khỏi LMS hoặc đổi phiên bản thì instance cũ không được chấm tiếp.
- Câu LLM tự do chỉ qua kiểm tra cấu trúc/KC/stage và guardrail; **chưa được chứng nhận đúng nội dung**. Không gọi grader để cấp mastery cho câu này; lưu phản hồi formative rồi chuyển sang anchor/biến thể đáng tin cậy cùng mức. Không đưa vào hàng chờ giảng viên chỉ vì nó formative.
- Timeout/JSON sai/cấu hình legacy lỗi → fallback; không coi lỗi hạ tầng là sinh viên yếu.

Giới hạn 16/2 giải quyết tăng sinh câu trong một phiên, **không thay thế chính sách retention toàn hệ thống**. Audit/evidence vẫn tăng theo số phiên thực tế. Chưa tự xóa dữ liệu: cần chốt thời hạn lưu, quyền truy cập và yêu cầu audit trước khi archive/purge production.

## 4. Kết quả thực tế

| Kiểm tra | Output thực tế | Ý nghĩa |
| --- | --- | --- |
| Toàn bộ backend `pytest tests` | **473 passed** | Regression kỹ thuật trên SQLite test riêng |
| Toàn bộ frontend Vitest | **168 passed**, 41 files | Checkpoint, editor, navigation và chức năng cũ |
| Ruff `src tests` | **All checks passed** | Lint backend/test |
| Production build | **PASS** | TypeScript và Vite; entry JS khoảng 343 kB trước gzip |
| Oracle đối chiếu independent truth table | PASS, 512 quan hệ × 6 tính chất | 3.072 phép đối chiếu trên tập ba phần tử |
| Transfer sinh dữ kiện | PASS, 30 trường hợp × 6 tính chất | Có thể giải; closure tối thiểu và counterexample phản đối xứng |
| Chuỗi generated qua API | PASS, cả 5 mức | Evidence lưu đúng snapshot, key riêng không lộ ra client |
| Reload / đổi phiên bản / scope | PASS | Câu ổn định trong phiên; stale submit trả 409; block khác có biến thể khác |
| LLM formative qua API | PASS | Không tạo thêm Knowledge Snapshot hoặc human review case; quay về anchor cùng mức |
| Teacher preview | PASS | Student 403, teacher xem được oracle, không tạo checkpoint; config sai 422 |
| Audit câu chưa trả lời | PASS | Reload không nhân đôi event; giữ câu đã hỏi |
| Provider thật, trước sửa transport timeout | Fallback sau **42,75 giây** | Phát hiện `model_copy` không đổi timeout/retry của HTTP client đã khởi tạo |
| Provider thật, sau sửa constructor | Fallback sau **8,16 giây**, 1 call, không sinh được câu | Xác minh fallback/timeout, **chưa xác minh chất lượng câu LLM thật** |

Provider probe chỉ dùng nội dung quan hệ bắc cầu tổng hợp, không gửi dữ liệu sinh viên hay gọi Google. Báo cáo test:

- [Backend JUnit](../evals/reports/question-design-backend-2026-10-09.xml)
- [Frontend JUnit](../evals/reports/question-design-frontend-2026-10-09.xml)
- [Provider probe](../evals/reports/question-design-provider-probe-2026-10-09.json)

Chạy lại backend bằng database **test riêng**, không dùng DB demo/production vì fixture có dọn bảng:

```powershell
$env:DATABASE_URL='sqlite:///./tmp/question-design-test-20261009.db'
.\.venv\Scripts\python.exe -m pytest tests -q
```

Frontend: trong `frontend/pacewise`, chạy `npm test` và `npm run build`.

## 5. Cách demo

1. Giảng viên mở **Thiết kế kiểm chứng**, sửa câu mẫu LMS thuộc Toán rời rạc.
2. Chọn KC đã xác nhận, nguồn, ít nhất hai tiêu chí rubric phù hợp các mức.
3. Chọn **Quan hệ hai ngôi — sinh biến thể có checker**, chọn tính chất, xem preview rồi duyệt.
4. Sinh viên vào study block đã áp dụng trong Do, mở checkpoint được map tới KC này.
5. Đúng và đủ bằng chứng thì sang mức tiếp theo; cần gợi ý/human review vẫn theo chính sách không chặn Plan–Do–Reflect.
6. Muốn dùng LLM follow-up thì cấu hình đoạn tham chiếu và câu anchor cho cùng mức. Nếu provider không phản hồi, câu anchor vẫn dùng được.

## 6. Chưa được chứng minh

- Chưa có semantic certification cho câu LLM tự do; nguồn metadata kế thừa không chứng minh câu generated đúng theo PDF.
- Chưa tự map property template vào KC bằng taxonomy; giảng viên chịu trách nhiệm cấu hình đúng concept/rubric.
- Chưa có corpus câu mở do chuyên gia chấm độc lập để đo agreement/false mastery/calibration.
- Chưa pilot sinh viên thật, chưa chứng minh learning gain hoặc independence.
- Không cá nhân hóa theo nhãn persona tùy tiện: hiện dùng KC, stage, evidence, hint và câu trả lời trước.
- Chưa rebuild Docker/backend đang chạy; kết quả trên là source/test/build local.

Kết luận: **controlled question-generation MVP được kiểm thử kỹ thuật**; không tuyên bố hệ thống đã chứng minh hiểu biết của người học trong production.
