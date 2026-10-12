# PaceWise — Brief

**Mã đề:** EDU-01 · **Đội:** P-008 · **Cập nhật:** 24/09/2026

## Bài toán

Canvas cho sinh viên biết **có việc gì và hạn khi nào**, nhưng chưa biến deadline thành kế hoạch tuần phù hợp với quỹ thời gian và mức độ hiểu bài. Khi một nhiệm vụ kéo dài hoặc kiến thức nền chưa vững, sinh viên thường phát hiện quá muộn, không biết dời việc nào và có thể làm vỡ cả kế hoạch tuần.

Khảo sát thăm dò 17 sinh viên ghi nhận nhu cầu về lịch, nhắc deadline, cảnh báo nguy cơ và gợi ý phần chưa nắm chắc; mẫu chỉ dùng để định hướng MVP.

## Người dùng mục tiêu

- **Sinh viên:** cần biết việc tiếp theo, kế hoạch còn khả thi không và phần vừa học đã hiểu tới đâu.
- **Giảng viên/cố vấn:** cần thấy sớm điểm nghẽn tiến độ và đơn vị kiến thức cần hỗ trợ qua dữ liệu tổng hợp.

## Giải pháp

PaceWise là trợ lý học tập theo chu trình **Plan–Do–Reflect**, giúp sinh viên tự điều chỉnh thay vì chỉ nhắc việc.

- **Plan:** đọc dữ liệu Canvas, chia assignment thành milestone và kiểm tra quỹ thời gian, phụ thuộc, deadline.
- **Lịch trong Kế hoạch:** timeline hợp nhất ca học/deadline LMS, study block đã xác nhận và khoảng không thể học. Google Calendar là kết nối tùy chọn để đọc busy/free và tạo study block sau xác nhận, còn `.ics` là fallback không cần OAuth.
- **Do:** ghi nhận thời gian thực tế và trả lời từ tài liệu môn học có trích dẫn.
- **Check trong Do:** dùng 1–3 câu đã duyệt để thu bằng chứng theo một đơn vị kiến thức.
- **Recover trong Do:** khi tiến độ, lịch bận hoặc dữ liệu LMS thay đổi, hệ thống tính lại capacity đa môn, tạo 2–3 phương án và chỉ đổi lịch sau khi sinh viên xác nhận. Deadline LMS luôn được giữ nguyên.
- **Reflect:** tổng kết đúng tuần học Thứ Hai–Chủ Nhật, so sánh dự kiến–thực tế, tìm nguyên nhân và chọn một điều chỉnh làm đầu vào cho bản nháp tuần sau. Mặc định mở Chủ Nhật 20:00 và không tự áp dụng kế hoạch khi sinh viên chưa xác nhận.
- **Giảng viên:** duyệt rubric, xem xu hướng tổng hợp và xử lý ca cần người xem.

MVP luôn chạy bằng dữ liệu Canvas mô phỏng. Canvas REST chỉ đọc chỉ bật khi có sandbox/token; LTI 1.3 là P1 khi trường cấp developer key.

## Vì sao cần AI và điểm mới

Điểm khác biệt là vòng kín **tiến độ → bằng chứng hiểu bài → hành động tiếp theo**. LLM chia nhỏ nhiệm vụ, xử lý câu trả lời mở và hỗ trợ phản tư; code kiểm tra quyền, deadline, xung đột, trích dẫn và audit.

PaceWise tham khảo “check for understanding” nhưng chỉ pilot một môn và 3–5 đơn vị kiến thức; mục tiêu và rubric do giảng viên/SME duyệt. Kết quả là bằng chứng kèm độ tin cậy, không phải điểm; ca không chắc chắn được chuyển cho giảng viên.

## Không làm trong MVP

- Không làm hộ, nộp bài, chấm điểm chính thức hoặc ghi điểm lên Canvas.
- Không đánh giá toàn bộ môn/ngành hay triển khai cấp trường.
- Không xếp hạng, kỷ luật hoặc tự động gắn nhãn “yếu/kém”.
- Không tự đổi lịch, gửi hỗ trợ cá nhân hoặc chia sẻ dữ liệu khi chưa có xác nhận.
- Không bắt buộc tài khoản Google trùng email trường và không làm PaceWise phụ thuộc vào một nhà cung cấp lịch.
- Không xác minh lý do sinh viên thay đổi lịch cá nhân, không quản lý giấy tờ y tế và không tự cấp gia hạn/thi bù; nếu không còn kế hoạch khả thi, hệ thống chỉ báo phần thiếu và khuyến nghị trao đổi với giảng viên.

## Đo thành công

Đây là **mục tiêu pilot, chưa phải kết quả đã đạt**. Ba bộ đánh giá độc lập đều có ít nhất 120 mẫu.

- **Sản phẩm:** nộp đúng hạn tăng ≥10 điểm phần trăm; ≥70% ca nguy cơ còn khả thi được phục hồi trước deadline; sai số dự kiến–thực tế giảm ≥20%; ≥60% bằng chứng dẫn tới hành động tiếp theo.
- **Plan/Recover:** ≥95% kế hoạch đúng ràng buộc; ≥90% ca có nghiệm bảo vệ deadline quan trọng.
- **Hiểu bài:** câu hỏi/đáp án hợp lệ ≥95%; bám mục tiêu ≥90%; chẩn đoán macro-F1 ≥0,80 so với nhãn chuyên gia.
- **Nguồn và liêm chính:** trích dẫn hợp lệ ≥95%; từ chối đúng khi thiếu nguồn ≥90%; đáp án làm hộ ≤5%; chặn nhầm ≤10%.
