# PaceWise — User Needs

**Phiên bản:** 1.0  
**Phạm vi:** Student Experience và Management Console của MVP

## 1. Jobs to be Done

### Sinh viên

> Khi có nhiều deadline và quỹ thời gian hữu hạn, tôi muốn biến các yêu cầu thành một kế hoạch tuần khả thi để biết việc tiếp theo và tránh phát hiện rủi ro quá muộn.

> Khi tiến độ thực tế lệch khỏi kế hoạch, tôi muốn xem các lựa chọn cùng đánh đổi để tự quyết định cách phục hồi mà không bị hệ thống tự đổi lịch.

> Khi không hiểu nội dung môn học, tôi muốn nhận câu trả lời có nguồn hoặc hướng dẫn từng bước để học tiếp mà không vi phạm liêm chính học thuật.

> Khi vừa học xong một chủ đề, tôi muốn biết bằng chứng hiện tại cho thấy mức hiểu của mình ra sao và nên làm gì tiếp theo.

> Cuối tuần, tôi muốn nhìn lại dữ kiện và chọn một thay đổi nhỏ cho tuần sau thay vì bị đánh giá về tính cách.

### Giảng viên/cố vấn

> Khi theo dõi một lớp, tôi muốn thấy xu hướng và ca cần xem với đủ căn cứ để hỗ trợ sớm nhưng không xâm phạm dữ liệu học tập riêng tư.

## 2. Nhu cầu theo mức ưu tiên

### P0 — Bắt buộc

| ID | Nhu cầu | Lý do |
|---|---|---|
| N-01 | Biết việc tiếp theo và lý do ưu tiên | Giá trị cốt lõi của dashboard |
| N-02 | Kế hoạch không vượt quỹ thời gian hoặc deadline | Tránh lịch giả và mất niềm tin |
| N-03 | Xem trước và xác nhận trước mọi thay đổi | Bảo toàn quyền kiểm soát |
| N-04 | Nhận biết dữ liệu, nguồn và giả định AI đã dùng | Giúp đánh giá đề xuất |
| N-05 | Có đường phục hồi khi tiến độ lệch | Giảm tác động dây chuyền của trễ hạn |
| N-06 | Phân biệt phản hồi học tập với điểm chính thức | Tránh gây áp lực và hiểu sai |
| N-07 | Citation mở đúng đoạn nguồn | Kiểm chứng câu trả lời |
| N-08 | Không bị cung cấp bài làm hoàn chỉnh để nộp | Liêm chính học thuật |
| N-09 | Không mất dữ liệu khi timeout hoặc lỗi AI | Phục hồi tác vụ an toàn |
| N-10 | Giao diện dùng được bằng bàn phím và screen reader | Khả năng tiếp cận cơ bản |

### P1 — Sau khi happy path ổn định

- Ghi nhớ tùy chọn qua nhiều tuần.
- Tích hợp Canvas REST/LTI thật.
- Thông báo theo tùy chọn của sinh viên.
- Cá nhân hóa khung giờ và hệ số ước lượng dài hạn.
- Mở rộng nhiều môn và so sánh tải học tập liên môn.

## 3. Nhu cầu chức năng theo workflow

### Plan

- Chọn tuần, assignment, mục tiêu, deadline và mức ưu tiên.
- Khai báo thời gian rảnh và khoảng không thể dùng.
- Xem milestone có đầu ra, thời lượng, phụ thuộc và deadline nội bộ.
- Xem tổng tải, xung đột, slack và giả định.
- Sửa một milestone mà không phải tạo lại toàn bộ kế hoạch.
- Không có nút lưu khi lịch vô nghiệm.

### Do/Tracking

- Xem việc tiếp theo, thời lượng và deadline.
- Bắt đầu/kết thúc phiên hoặc nhập thời gian thủ công.
- Sửa dữ liệu thực tế bị ghi sai.
- Hiểu cảnh báo được tạo từ dữ kiện nào.
- Bỏ qua cảnh báo hoặc mở Recover.

### Q&A

- Đặt câu hỏi bằng ngôn ngữ tự nhiên.
- Biết câu trả lời có đủ nguồn hay không.
- Mở citation mà không mất câu hỏi đang soạn.
- Báo nguồn sai.
- Nhận hướng dẫn thay thế khi yêu cầu bị chặn.

### Understanding

- Chọn đơn vị kiến thức và làm 1–3 câu.
- Xem bốn khía cạnh cùng bằng chứng.
- Biết độ tin cậy và giới hạn của kết luận.
- Nhận một hành động tiếp theo.
- Gửi ca không chắc chắn cho giảng viên xem.

### Recover

- So sánh 2–3 phương án trên cùng tiêu chí.
- Biết việc giữ, việc dời, giờ thiếu/dư, deadline và rủi ro.
- Xem diff trước–sau trước khi xác nhận.
- Có lựa chọn bỏ qua mà không mất kế hoạch cũ.

### Reflect

- So sánh kế hoạch và thực tế bằng dữ kiện.
- Trả lời tối đa ba câu ngắn.
- Chọn đúng một điều chỉnh đo được cho tuần sau.
- Lưu phản tư mà không bắt buộc áp dụng điều chỉnh.

## 4. Nhu cầu cảm xúc và niềm tin

- Ngôn ngữ trung lập, không gắn nhãn “lười”, “kém” hoặc “thiếu kỷ luật”.
- Cảnh báo phải tạo cảm giác còn lựa chọn, không đe dọa.
- Khi AI không chắc chắn, nói rõ thay vì tạo câu trả lời tự tin giả.
- Người dùng luôn biết dữ liệu đã được lưu hay chưa.
- Có thể quay lại quyết định trước qua audit/snapshot khi phạm vi cho phép.
- Không dùng dark pattern để ép xác nhận đề xuất AI.

## 5. Nhu cầu khả năng tiếp cận

- Tương phản văn bản và control đạt WCAG 2.1 AA.
- Không dùng màu làm tín hiệu trạng thái duy nhất.
- Focus nhìn thấy rõ và thứ tự tab hợp logic.
- Form có label, mô tả lỗi và liên kết lỗi tới trường tương ứng.
- Loading dùng `aria-live`; modal giữ focus và trả focus khi đóng.
- Touch target tối thiểu khoảng 44 × 44 px.
- Ngày giờ có timezone; số phần trăm đi cùng mẫu số khi cần.
- Biểu đồ có bảng hoặc mô tả dữ liệu tương đương.

## 6. Ràng buộc và nguyên tắc sản phẩm

- MVP chạy được bằng Canvas fixture; không phụ thuộc credential thật.
- Không tự nộp bài, đổi deadline, ghi điểm hoặc gửi email.
- Không ghi kế hoạch, Recover hay điều chỉnh Reflect trước xác nhận.
- Không hiển thị dữ liệu tổng hợp của nhóm dưới 5 người.
- Không lưu analytics chứa chat, câu trả lời hoặc phản tư thô.
- Timeout không được tạo thao tác ghi trùng khi người dùng thử lại.

## 7. Chỉ số UX

| Chỉ số | Mục tiêu pilot |
|---|---:|
| Hoàn thành tác vụ tạo và xác nhận Plan | ≥80% không cần trợ giúp |
| Nhận biết đúng trạng thái “chưa lưu” | ≥80% |
| Chọn được Recover và giải thích đúng đánh đổi | ≥80% |
| Tìm/mở đúng citation | ≥90% |
| Phân biệt Check với điểm chính thức | ≥80% |
| Tỷ lệ lỗi do bấm nhầm xác nhận | ≤5% |
| System Usability Scale tham khảo | ≥70 |

