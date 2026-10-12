# PaceWise — UX Personas

**Phiên bản:** 1.0  
**Phạm vi:** MVP một môn pilot  
**Nguồn:** Brief, PRD và khảo sát thăm dò 17 sinh viên của dự án

> Đây là proto-persona dùng để định hướng thiết kế, chưa phải kết luận nghiên cứu đại diện. Các giả định cần được kiểm chứng qua usability test với sinh viên và giảng viên thật.

## 1. Persona chính — Minh, sinh viên thường xuyên bị dồn deadline

### Hồ sơ

| Thuộc tính | Mô tả |
|---|---|
| Vai trò | Sinh viên đại học năm 2–3 |
| Thiết bị chính | Điện thoại khi theo dõi; laptop khi viết bài |
| Bối cảnh | Học nhiều môn, dùng Canvas nhưng vẫn tự quản lý lịch bằng ghi chú rời rạc |
| Kỹ năng số | Khá; quen chatbot nhưng không hiểu sâu cách AI tạo câu trả lời |
| Thời gian học | Phân mảnh, thay đổi theo lịch học và việc cá nhân |

### Mục tiêu

- Biết việc quan trọng nhất cần làm tiếp theo.
- Chuyển assignment lớn thành các bước đủ nhỏ để bắt đầu.
- Có kế hoạch tuần không vượt quỹ thời gian thực tế.
- Phát hiện nguy cơ trước khi quá sát deadline.
- Nhận trợ giúp để hiểu bài mà không nhận bài làm hộ.
- Điều chỉnh kế hoạch nhưng vẫn giữ quyền quyết định cuối cùng.

### Khó khăn

- Đánh giá thấp thời gian cần để đọc và viết.
- Thấy danh sách deadline nhưng không biết thứ tự ưu tiên.
- Dễ dành quá lâu cho một nhiệm vụ rồi làm vỡ lịch còn lại.
- Không biết câu trả lời của AI có dựa đúng tài liệu môn học hay không.
- Cảm thấy áp lực nếu sản phẩm dùng ngôn ngữ phán xét.
- Lo AI tự thay đổi lịch hoặc chia sẻ dữ liệu cá nhân.

### Hành vi điển hình

- Kiểm tra deadline trên điện thoại, nhưng làm bài trên laptop.
- Chỉ lập kế hoạch chi tiết khi deadline đã gần.
- Ưu tiên việc dễ hoàn thành thay vì việc có rủi ro cao.
- Muốn sửa nhanh đề xuất của AI thay vì nhập lại từ đầu.
- Cần thấy lý do và ảnh hưởng trước khi xác nhận thay đổi.

### Trích dẫn đại diện

> “Tôi không thiếu danh sách việc cần làm; tôi cần biết việc nào phải bắt đầu trước và liệu lịch này có thực tế không.”

### Nhu cầu thiết kế

- Dashboard trả lời ngay “Việc tiếp theo là gì?” và “Tại sao?”.
- Các kế hoạch luôn có nhãn **Bản xem trước — chưa lưu** trước xác nhận.
- Deadline tương đối phải được chuyển thành ngày giờ cụ thể.
- Cảnh báo trình bày theo cấu trúc dữ kiện → ảnh hưởng → lựa chọn.
- Mọi thay đổi lịch đều có diff trước–sau và có thể hủy.
- Giao diện hoạt động tốt ở 360 px và tiếp tục liền mạch trên desktop.

## 2. Persona phụ — Lan, sinh viên muốn biết mình đã hiểu bài chưa

### Hồ sơ

| Thuộc tính | Mô tả |
|---|---|
| Vai trò | Sinh viên năm nhất trong môn pilot |
| Bối cảnh | Chăm học nhưng khó tự đánh giá chất lượng câu trả lời mở |
| Thái độ với AI | Sẵn sàng dùng nếu có nguồn và giới hạn rõ ràng |

### Mục tiêu

- Kiểm tra nhanh một đơn vị kiến thức trước khi chuyển chủ đề.
- Biết điểm nào trong lập luận cần cải thiện.
- Nhận một hành động học tiếp theo cụ thể.
- Không bị gắn nhãn năng lực hoặc tạo điểm số không chính thức.

### Khó khăn

- Dễ nhầm phản hồi AI với điểm chính thức.
- Không biết độ tin cậy của đánh giá.
- Có thể đưa câu trả lời quá ngắn nhưng vẫn mong kết luận chắc chắn.
- Khó tìm lại đúng đoạn tài liệu liên quan.

### Nhu cầu thiết kế

- Dùng bốn trạng thái bằng chứng, không dùng thang điểm hoặc xếp hạng.
- Hiển thị trích đoạn từ chính câu trả lời làm bằng chứng.
- Nêu độ tin cậy, giới hạn và lý do chưa thể kết luận.
- Cho phép yêu cầu giảng viên xem khi kết quả không chắc chắn.
- Luôn có đúng một bước học tiếp theo nổi bật.

## 3. Persona hỗ trợ — Thầy Nam, giảng viên/cố vấn

### Hồ sơ

| Thuộc tính | Mô tả |
|---|---|
| Vai trò | Giảng viên môn pilot hoặc cố vấn học tập |
| Bối cảnh | Theo dõi nhiều sinh viên, ít thời gian xem từng trường hợp |
| Thiết bị chính | Laptop/desktop |

### Mục tiêu

- Nhìn thấy xu hướng lớp trước khi vấn đề trở nên nghiêm trọng.
- Duyệt mục tiêu, câu hỏi và rubric trước khi sử dụng.
- Xử lý nhanh ca độ tin cậy thấp hoặc nguồn bị phản ánh.
- Chỉ can thiệp cá nhân khi có đủ căn cứ và đã xác nhận.

### Khó khăn

- Dashboard dễ biến thành công cụ giám sát quá mức.
- Dữ liệu tổng hợp có thể gây hiểu sai nếu mẫu quá nhỏ.
- Không có thời gian đọc nội dung chat hoặc phản tư thô.
- Cần biết dữ liệu nào đã dẫn đến cảnh báo.

### Nhu cầu thiết kế

- Chỉ hiển thị tổng hợp khi `n ≥ 5`.
- Không hiển thị chat hoặc phản tư thô.
- Hàng chờ có lý do, bằng chứng, độ tin cậy và hành động rõ ràng.
- Mọi hỗ trợ hướng tới cá nhân đều có bước xem trước và xác nhận.
- Biểu đồ phải có bảng dữ liệu tương đương cho khả năng tiếp cận.

## 4. Anti-persona và đối tượng ngoài phạm vi

- Người muốn hệ thống làm và nộp toàn bộ bài tính điểm.
- Quản trị viên muốn dùng dữ liệu để xếp hạng hoặc kỷ luật sinh viên.
- Người dùng kỳ vọng PaceWise thay đổi điểm hoặc deadline trên Canvas.
- Triển khai toàn trường, đa ngôn ngữ và đa môn đầy đủ trong MVP.

## 5. Giả định cần kiểm chứng

| Giả định | Cách kiểm chứng | Tín hiệu đạt |
|---|---|---|
| Sinh viên hiểu “bản xem trước” chưa làm đổi lịch | Usability task xác nhận Plan | ≥80% trả lời đúng không cần gợi ý |
| Sinh viên hiểu bốn trạng thái không phải điểm | Phỏng vấn sau task Check | ≥80% mô tả đúng mục đích |
| Diff trước–sau đủ để chọn Recover | Task chọn phương án | ≥80% chọn và giải thích được đánh đổi |
| Citation tạo niềm tin và được mở khi cần | Theo dõi click + phỏng vấn | Người dùng tìm đúng nguồn trong ≤30 giây |
| Giảng viên chấp nhận ngưỡng `n ≥ 5` | Interview với giảng viên | Không yêu cầu lộ dữ liệu cá nhân ngoài luồng duyệt |

