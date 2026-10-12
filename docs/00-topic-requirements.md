# PaceWise — Yêu cầu đề tài và truy vết

**Mã đề:** EDU-01 · **Đội:** P-008 · **Cập nhật:** 24/09/2026
Tài liệu này là nguồn chuẩn để kiểm tra scope, kiến trúc và cách đánh giá. Khi đổi quyết định, đội phải sửa tài liệu này cùng PR với code.

## 1. Bài toán

Sinh viên học nhiều môn trên Canvas có thể nhìn thấy assignment và deadline, nhưng vẫn phải tự biến chúng thành một kế hoạch tuần phù hợp với quỹ thời gian, mức ưu tiên và mức độ hiểu bài. Khi một nhiệm vụ kéo dài hơn dự kiến hoặc kiến thức nền chưa vững, sinh viên thường phát hiện quá muộn, không biết dời việc nào và có thể làm vỡ cả kế hoạch tuần.

PaceWise giải quyết lát cắt sau:

> Giúp sinh viên lập kế hoạch khả thi, phát hiện sai lệch sớm, phục hồi kế hoạch trước deadline và dùng bằng chứng học tập để chọn hành động tiếp theo.

Chu trình chính vẫn là **Plan → Do → Reflect**. “Check” và “Recover” là hai cơ chế bên trong bước **Do**, không phải hai giai đoạn mới thay thế đề bài:

- **Plan:** lấy nhiệm vụ, deadline và quỹ thời gian để tạo kế hoạch tuần.
- **Do:** thực hiện nhiệm vụ; theo dõi thời gian, hỏi đáp có nguồn, kiểm tra nhanh mức hiểu bài và phục hồi kế hoạch khi bị lệch.
- **Reflect:** đối chiếu kế hoạch với thực tế, tìm nguyên nhân và điều chỉnh tuần sau.

## 2. Người dùng và hai giao diện

| Vai trò | Nhu cầu | Quyền chính |
|---|---|---|
| Sinh viên | Biết việc tiếp theo, nguy cơ trễ, phần chưa nắm chắc và cách điều chỉnh | Xem dữ liệu cá nhân; tạo/xác nhận kế hoạch; cập nhật tiến độ; làm kiểm tra nhanh; phản tư |
| Giảng viên/cố vấn | Thấy xu hướng tiến độ và điểm nghẽn của lớp mà không đọc dữ liệu riêng tư không cần thiết | Duyệt câu hỏi/rubric; xem số liệu tổng hợp; xem hàng chờ cần hỗ trợ; xác nhận can thiệp |

Hai giao diện dùng chung backend và mô hình phân quyền. Dashboard giảng viên chỉ hiển thị dữ liệu tổng hợp khi nhóm có **ít nhất 5 sinh viên**.

## 3. Phạm vi đã khóa

### P0 — bắt buộc cho MVP

- Pilot **1 môn học** với **3–5 đơn vị kiến thức** đã được giảng viên/SME duyệt.
- Đăng nhập mô phỏng và phân quyền sinh viên/giảng viên.
- Nhập nhiệm vụ từ bộ dữ liệu Canvas mô phỏng; có thể dùng Canvas REST chỉ đọc khi có sandbox/token.
- Tạo kế hoạch tuần có milestone, ước lượng thời gian, ưu tiên và ràng buộc deadline.
- Lịch nội bộ luôn hoạt động; sinh viên có thể kết nối Google Calendar để đọc busy/free và xuất study block, hoặc tải `.ics` mà không cần OAuth.
- Theo dõi thời gian dự kiến–thực tế, phát hiện nguy cơ và tạo phương án phục hồi.
- Hỏi đáp từ tài liệu môn học, luôn kèm nguồn hoặc từ chối khi thiếu nguồn.
- Kiểm tra nhanh 1–3 câu, tạo bằng chứng học tập và gợi ý bước tiếp theo.
- Phản tư cuối tuần.
- Dashboard giảng viên dạng tổng hợp, có hàng chờ duyệt và bước xác nhận trước khi hỗ trợ.
- Logging, metrics, tracing, đánh giá offline và triển khai online.

### P1 — chỉ làm khi P0 vượt release gate

- Canvas REST read-only chạy với sandbox/token thật.
- LTI 1.3 khi trường cấp developer key và môi trường thử nghiệm.
- Memory dài hạn qua nhiều tuần.
- Reranker dịch vụ bên ngoài hoặc model lớn cho ca phản tư khó.
- Load test đến 1.000 người dùng đồng thời.

### Không làm

- Không làm hộ, nộp bài, chấm điểm chính thức hoặc ghi điểm ngược lên Canvas.
- Không thay thế LMS, không fork Canvas và không triển khai toàn trường trong MVP.
- Không đánh giá toàn bộ chương trình học.
- Không xếp hạng, kỷ luật hoặc tự động gắn nhãn “yếu/kém”.
- Không gửi thông báo, đổi lịch, chia sẻ dữ liệu hay can thiệp mà chưa có xác nhận cần thiết.

## 4. Hợp đồng tích hợp Canvas

Quy tắc thống nhất trong toàn bộ tài liệu:

> MVP luôn hoạt động với Canvas fixture. Canvas REST chỉ đọc chỉ được bật khi có sandbox/token. LTI 1.3 là P1 khi có developer key.

PaceWise chỉ đọc course, assignment, syllabus và submission status cần thiết. Dữ liệu mô phỏng có cùng schema với adapter thật để không phải viết lại nghiệp vụ. Nếu mất kết nối Canvas, hệ thống dùng dữ liệu đồng bộ gần nhất, hiển thị thời điểm cập nhật và không giả vờ dữ liệu đang mới.

## 5. Kiến trúc AI đã khóa

### Thành phần bắt buộc

- **FastAPI** cho API; **Next.js/React** cho hai giao diện.
- **LangGraph** điều phối Plan, Do, Recover và Reflect; các ràng buộc lịch, quyền, schema và tính toán KPI do code xác định.
- **OpenRouter** làm cổng model; GPT-4o-mini hoặc Claude Haiku cho tác vụ thường, model lớn chỉ dùng cho ca Reflect khó sau khi bộ định tuyến cho phép.
- **Qdrant** lưu vector tài liệu môn; embedding đa ngôn ngữ; **bge-reranker** là mặc định, Cohere Rerank là cấu hình thay thế.
- **PostgreSQL** lưu dữ liệu nghiệp vụ và lịch sử; **Redis** cache, rate limit và hàng đợi ngắn.
- Guardrail ba lớp: quy tắc nhanh + semantic classifier hiệu chuẩn + policy kiểm tra output. Khi classifier lỗi, yêu cầu mơ hồ được hạ cấp sang guided help an toàn.
- **RAGAS**, metric xác định trước và LLM-as-Judge đã hiệu chuẩn cho đánh giá.
- Docker; staging/production trên Render hoặc GCP Cloud Run tùy ngân sách đã chốt.

### Ranh giới AI và phần mềm thường

AI dùng cho chia nhỏ nhiệm vụ, giải thích nội dung, xử lý câu trả lời mở, nhận diện mẫu sai và hỗ trợ phản tư. Code thường chịu trách nhiệm cho xác thực, phân quyền, tính deadline, kiểm tra xung đột lịch, ngưỡng ẩn danh, schema, audit log và hành động có tác động.

Mọi thay đổi stack phải có benchmark tối thiểu, lý do, người duyệt và cập nhật tài liệu trong cùng PR.

## 6. Đánh giá mức độ hiểu bài

PaceWise đo **bằng chứng học tập mang tính hỗ trợ**, không tạo điểm chính thức. Với mỗi đơn vị kiến thức, hệ thống đánh giá bốn mặt:

1. Đúng khái niệm.
2. Lập luận hoặc giải thích được.
3. Vận dụng vào tình huống gần.
4. Có lỗ hổng kiến thức nền hay không.

Kết quả thuộc một trong bốn trạng thái: **chưa đủ bằng chứng**, **còn nhầm lẫn**, **đang hình thành**, **đã thể hiện được**; kèm độ tin cậy và nguồn bằng chứng. Nếu độ tin cậy thấp hoặc tín hiệu mâu thuẫn, hệ thống từ chối kết luận và chuyển vào hàng chờ giảng viên.

Quy trình tạo nhãn chuẩn:

- Chọn 1 môn và 3–5 đơn vị kiến thức.
- Giảng viên/SME duyệt mục tiêu, đáp án và rubric.
- Hai người gán nhãn độc lập; người thứ ba phân xử bất đồng.
- Báo cáo mức đồng thuận giữa người chấm.
- Bộ kiểm thử có ít nhất 120 mẫu và được quản lý phiên bản.

## 7. Hợp đồng đánh giá

Ba bộ dữ liệu độc lập, mỗi bộ có **ít nhất 120 mẫu**:

| Bộ dữ liệu | Nội dung | Chỉ số chính |
|---|---|---|
| `planning_v1` | Ca bình thường, quá tải, nguy cơ trễ và phục hồi | Đúng ràng buộc ≥95%; bảo vệ deadline quan trọng ≥90% khi còn nghiệm; risk recall ≥85%, precision ≥75% |
| `grounding_safety_v1` | Có/không có câu trả lời, prompt injection, yêu cầu hợp lệ và yêu cầu làm hộ | Trích dẫn hợp lệ ≥95%; từ chối đúng khi thiếu nguồn ≥90%; trả lời làm hộ ≤5%; chặn nhầm ≤10% |
| `understanding_journey_v1` | Chất lượng câu hỏi, câu trả lời có nhầm lẫn và hành trình Plan–Do–Reflect | Câu hỏi/đáp án hợp lệ ≥95%; bám mục tiêu ≥90%; chẩn đoán macro-F1 ≥0,80; lỗi ở ca độ tin cậy cao ≤5% |

Ngưỡng hiệu năng:

- Hỏi đáp p95 ≤8 giây.
- Plan/Recover p95 ≤15 giây.
- Hard timeout 30 giây; luôn có trạng thái đang xử lý và phương án thử lại.
- Báo cáo token, chi phí mỗi tác vụ, cache hit và tỷ lệ chuyển model.
- P0 kiểm thử 100 virtual users; 1.000 người đồng thời là mục tiêu nâng cao.

KPI sản phẩm của pilot, không phải tuyên bố đã đạt:

- Tỷ lệ nộp đúng hạn tăng **ít nhất 10 điểm phần trăm** so với baseline cùng nhóm/môn.
- Ít nhất **70%** ca có nguy cơ nhưng còn khả thi được sinh viên xác nhận phương án phục hồi trước deadline.
- Trung vị sai số giữa thời gian dự kiến và thực tế giảm **ít nhất 20%** sau ba tuần.
- Ít nhất **60%** bằng chứng học tập dẫn tới một hành động tiếp theo.

## 8. Quyền riêng tư và Human-in-the-loop

- Dashboard chỉ tổng hợp nhóm `n ≥ 5`; không hiển thị nội dung chat/phản tư thô.
- Log vận hành giữ 30 ngày; dữ liệu pilot đã thay định danh giữ 90 ngày.
- Yêu cầu xóa dữ liệu được xử lý trong 30 ngày; bản sao lưu hết hạn trong 30 ngày tiếp theo.
- Không dùng dữ liệu để xếp hạng, kỷ luật hoặc chấm điểm chính thức.
- Sinh viên phải xác nhận trước khi ghi kế hoạch mới hoặc phục hồi lịch.
- Sinh viên phải xác nhận trước khi PaceWise tạo sự kiện Google; kết nối có thể dùng tài khoản Google cá nhân khác email trường và luôn có nút thu hồi quyền.
- Giảng viên duyệt mục tiêu, câu hỏi và rubric; xác nhận trước mọi hành động hỗ trợ hướng tới cá nhân.

## 9. Quyết định còn mở

| Quyết định | Người chịu trách nhiệm | Hạn chốt |
|---|---|---|
| Môn pilot và 3–5 đơn vị kiến thức | PO + BA | Cuối tuần 1 |
| Giảng viên/SME duyệt nội dung | BA | Cuối tuần 1 |
| Canvas sandbox/token/developer key | Tech Lead | Cuối tuần 1 |
| Provider, model và phiên bản prompt | AI Engineer | Đầu tuần 3 |
| Nơi deploy và ngân sách pilot | Tech Lead + PO | Cuối tuần 2 |
| Xác nhận stack bắt buộc hoặc ngoại lệ | Tech Lead + mentor | Cuối tuần 1 |

Nếu một điều kiện chưa được đáp ứng đúng hạn, đội dùng phương án P0 tương ứng: fixture thay REST, web độc lập thay LTI, model/reranker cục bộ thay dịch vụ.

## 10. Thuật ngữ

| Thuật ngữ | Cách dùng trong tài liệu |
|---|---|
| Learning component | Đơn vị kiến thức |
| Evidence state | Trạng thái bằng chứng học tập |
| Response pattern | Mẫu trả lời |
| Ground truth | Nhãn chuẩn |
| Abstain | Từ chối kết luận |
| Review queue | Hàng chờ giảng viên |
| Recovery | Phục hồi kế hoạch |
| Confidence | Độ tin cậy |

## 11. Truy vết tài liệu

- Bài toán và định vị: [01-brief.md](./01-brief.md)
- Yêu cầu có thể code/test: [02-prd.md](./02-prd.md)
- Màn hình và trạng thái: [03-wireframe-uiflow.md](./03-wireframe-uiflow.md)
- Phân công và tiến độ: [04-project-charter.md](./04-project-charter.md)
- Kiến trúc: [architecture_diagram.md](./architecture_diagram.md)
