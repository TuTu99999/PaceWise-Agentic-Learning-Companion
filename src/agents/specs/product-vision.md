| Agent | Chức năng chính | Đầu vào | Đầu ra |
|---|---|---|---|
| **Coordinator Agent** | Nhận yêu cầu, chọn workflow Plan / Do / Q&A / Check Understanding / Recover / Reflect; điều phối node tiếp theo. | Ý định người dùng, state phiên hiện tại | workflow, next_node |
| **Milestone Agent** | Chia assignment thành milestone nhỏ, có đầu ra kiểm chứng được; ước lượng thời lượng và nêu phụ thuộc. | Assignment, deadline, mục tiêu, thời gian khả dụng | Danh sách milestone đề xuất |
| **Study Support Agent** | Trả lời câu hỏi dựa trên đoạn tài liệu được truy xuất; đưa gợi ý phù hợp với quy tắc liêm chính học thuật. | Câu hỏi, ngữ cảnh nhiệm vụ, các đoạn nguồn | Câu trả lời, trích dẫn, hoặc lý do chưa thể trả lời |
| **Understanding Agent** | Phân tích câu trả lời mở theo rubric; tìm bằng chứng về khái niệm, lập luận, vận dụng và kiến thức nền. | Câu trả lời của sinh viên, rubric, câu hỏi | Nhận xét có cấu trúc và bằng chứng |
| **Recovery Agent** | Đề xuất và diễn giải các phương án khôi phục khi kế hoạch lệch; trình bày đánh đổi và rủi ro còn lại. | Snapshot, tín hiệu nguy cơ, các lịch hợp lệ | Các phương án Recover để xem trước |
| **Reflection Agent** | Tóm tắt tuần học từ dữ liệu và phản hồi của sinh viên; đề xuất một thay đổi cho tuần sau. | Kế hoạch, thực tế, bằng chứng học tập, tối đa ba câu phản tư | Bản tổng kết và điều chỉnh đề xuất | 

### 5.2 Plan — lập kế hoạch tuần

1. Sinh viên chọn tuần, mục tiêu, quỹ thời gian từng ngày và khung giờ không thể dùng.
2. Bộ lập lịch xác định trước kiểm tra deadline, thời lượng và phụ thuộc.
3. LLM đề xuất cách chia assignment thành milestone có đầu ra kiểm chứng được.
4. Bộ kiểm tra schema và lịch loại phương án vượt quỹ thời gian, đặt sau deadline hoặc thiếu phụ thuộc.
5. Hệ thống xếp ưu tiên theo deadline, trọng số do người dùng cung cấp, tiến độ và mức rủi ro.
6. Sinh viên thấy bản xem trước gồm lý do ưu tiên, slot học, phần chưa chắc chắn và cảnh báo quá tải.
7. Sinh viên sửa hoặc xác nhận. Chỉ sau xác nhận, kế hoạch mới được lưu.

**Trường hợp không khả thi:** hệ thống không tạo lịch giả. Nó chỉ rõ thiếu bao nhiêu giờ và yêu cầu sinh viên giảm phạm vi, đổi ưu tiên hoặc trao đổi với giảng viên.

### 5.3 Do — thực hiện và theo dõi

1. Dashboard hiển thị việc tiếp theo, thời lượng dự kiến, deadline và trạng thái.
2. Sinh viên bắt đầu/kết thúc phiên hoặc nhập thời gian thực tế.
3. Bộ tính sai lệch cập nhật:
   - phần trăm hoàn thành;
   - sai số thời gian;
   - slack trước deadline;
   - số milestone bị phụ thuộc;
   - trạng thái bằng chứng học tập liên quan.
4. Nếu vượt ngưỡng, hệ thống tạo tín hiệu nguy cơ và giải thích dữ liệu đã dùng.
5. Sinh viên có thể tiếp tục, mở Recover hoặc đánh dấu dữ liệu chưa đúng.

### 5.4 Do — hỏi đáp có nguồn và liêm chính

1. Câu hỏi được kiểm tra prompt injection và ý định làm hộ.
2. Với yêu cầu hợp lệ, retriever tìm đoạn liên quan trong Qdrant; reranker xếp lại.
3. Nếu nguồn không đủ, hệ thống từ chối trả lời chắc chắn và gợi ý tài liệu cần xem.
4. Nếu đủ nguồn, LLM trả lời ngắn, kèm trích dẫn đến tài liệu/đoạn.
5. Với yêu cầu làm hộ bài tính điểm, hệ thống không sinh đáp án hoàn chỉnh; yêu cầu sinh viên đưa cách làm thử, đưa gợi ý từng bước hoặc giải thích khái niệm.
6. Người dùng có thể báo trích dẫn sai; sự kiện được đưa vào bộ đánh giá.

### 5.5 Do — kiểm tra mức hiểu bài

1. Sinh viên chọn một đơn vị kiến thức hoặc hệ thống gợi ý từ nhiệm vụ đang làm.
2. Hệ thống lấy mục tiêu, ngân hàng câu hỏi/rubric đã được giảng viên duyệt.
3. Sinh viên làm 1–3 câu; với câu mở, AI chỉ phân tích theo rubric.
4. Bộ chấm xác định trước xử lý câu đóng; AI xử lý câu mở và phải trả schema.
5. Hệ thống tổng hợp bốn mặt: đúng khái niệm, lập luận, vận dụng và kiến thức nền.
6. Kết quả là một trong bốn trạng thái:
   - chưa đủ bằng chứng;
   - còn nhầm lẫn;
   - đang hình thành;
   - đã thể hiện được.
7. Mỗi kết quả có nguồn bằng chứng, độ tin cậy, giới hạn và hành động tiếp theo.
8. Nếu độ tin cậy thấp, câu trả lời mâu thuẫn hoặc nội dung ngoài rubric, hệ thống từ chối kết luận và đưa vào hàng chờ giảng viên.

Kết quả không được hiển thị như điểm số và không ghi vào gradebook.

### 5.6 Do — Recover

Recover được kích hoạt khi có ít nhất một điều kiện:

- slack của deadline quan trọng xuống dưới ngưỡng;
- một milestone vượt thời gian dự kiến;
- nhiệm vụ phụ thuộc bị chậm;
- bằng chứng học tập cho thấy cần thêm một phiên ôn;
- sinh viên chủ động yêu cầu.

Luồng:

1. Hệ thống chụp snapshot kế hoạch hiện tại.
2. Bộ lập lịch tạo các phương án hợp lệ; LLM diễn giải đánh đổi.
3. Mỗi phương án nêu việc giữ, việc dời, thời gian thiếu/dư, deadline được bảo vệ và rủi ro còn lại.
4. Nếu không còn nghiệm khả thi, hệ thống nói rõ và gợi ý trao đổi với giảng viên.
5. Sinh viên chọn, sửa hoặc bỏ qua.
6. Màn hình xác nhận hiển thị diff trước–sau.
7. Chỉ sau xác nhận, lịch mới được cập nhật; snapshot cũ vẫn nằm trong audit log.

### 5.7 Reflect — cuối tuần

1. Hệ thống tổng hợp kế hoạch, thời gian thực tế, milestone, tín hiệu nguy cơ và bằng chứng học tập.
2. Sinh viên trả lời tối đa ba câu: điều gì hiệu quả, điều gì gây lệch, tuần sau đổi gì.
3. AI tóm tắt nhưng không phán xét tính cách/năng lực.
4. Sinh viên chọn một điều chỉnh: hệ số ước lượng, khung giờ, cách chia việc hoặc đơn vị kiến thức cần ôn.
5. Điều chỉnh chỉ ảnh hưởng kế hoạch tuần sau sau khi sinh viên xác nhận.