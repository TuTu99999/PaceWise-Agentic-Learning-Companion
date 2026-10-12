# PaceWise — UX Writing và Microcopy

**Phiên bản:** 1.0

## 1. Voice và tone

PaceWise nói như một người đồng hành rõ ràng, bình tĩnh và tôn trọng quyền quyết định.

### Nguyên tắc

- Dùng dữ kiện, không phán xét con người.
- Nêu hành động cụ thể thay vì lời động viên chung chung.
- Minh bạch về nguồn, giả định và mức không chắc chắn.
- Không nhân hóa AI quá mức hoặc tuyên bố chắc chắn tuyệt đối.
- Dùng “bạn” và câu chủ động; tránh thuật ngữ kỹ thuật nội bộ.

### Tránh và nên dùng

| Tránh | Nên dùng |
|---|---|
| Bạn đang học quá kém | Thời gian thực tế tuần này thấp hơn kế hoạch 3 giờ |
| AI đã quyết định lịch tốt nhất | Đây là một phương án dựa trên deadline và thời gian bạn cung cấp |
| Có lỗi xảy ra | Chưa thể tạo kế hoạch; dữ liệu bạn nhập vẫn được giữ lại |
| OK | Xác nhận và lưu |
| Điểm hiểu bài: 7/10 | Trạng thái bằng chứng: đang hình thành |
| Bạn gian lận | Mình không thể tạo bài hoàn chỉnh để nộp |

## 2. CTA chuẩn

| Mục đích | Nhãn |
|---|---|
| Tạo bản nháp | Tạo kế hoạch |
| Ghi kế hoạch | Xác nhận và lưu |
| Mở Recover | Xem phương án phục hồi |
| Ghi lịch mới | Xác nhận cập nhật |
| Gửi câu hỏi | Gửi câu hỏi |
| Mở nguồn | Mở đoạn nguồn |
| Phản ánh citation | Báo nguồn sai |
| Gửi hàng chờ | Gửi giảng viên xem |
| Lưu Reflect không áp dụng | Chỉ lưu phản tư |
| Áp dụng tuần sau | Dùng cho tuần sau |
| Retry | Thử lại |
| Bỏ thay đổi | Giữ kế hoạch hiện tại |

Không dùng “Có/Không” khi hành động có thể được gọi tên rõ hơn.

## 3. Plan

### Empty

**Tiêu đề:** Chưa có kế hoạch cho tuần này  
**Mô tả:** Thêm mục tiêu, deadline và thời gian rảnh để tạo một kế hoạch có thể kiểm tra.  
**CTA:** Tạo kế hoạch

### Processing

**Tiêu đề:** Đang tạo bản nháp kế hoạch  
**Mô tả:** PaceWise đang chia nhiệm vụ và kiểm tra deadline, thời lượng cùng phụ thuộc.

### Preview

**Nhãn:** Bản xem trước — chưa lưu  
**Mô tả:** Kiểm tra các mốc, thời gian và giả định trước khi áp dụng.

### Infeasible

**Tiêu đề:** Quỹ thời gian hiện tại chưa đủ  
**Mô tả:** Các nhiệm vụ cần khoảng `{required_hours}` giờ, nhưng bạn còn `{available_hours}` giờ trước deadline. Bạn đang thiếu khoảng `{deficit_hours}` giờ.

### Saved

**Tiêu đề:** Kế hoạch đã được lưu  
**Mô tả:** Thay đổi có hiệu lực từ `{effective_date}`. Bạn vẫn có thể chỉnh sửa từng milestone.

## 4. Tracking và Recover

### Risk

**Tiêu đề:** Kế hoạch có nguy cơ lệch  
**Dữ kiện:** `{milestone}` đã dùng `{actual}` phút so với `{planned}` phút dự kiến.  
**Ảnh hưởng:** Nếu giữ nhịp hiện tại, thời gian đệm trước `{deadline}` còn `{slack}`.  
**Lựa chọn:** Bạn có thể sửa dữ liệu, tiếp tục hoặc xem phương án phục hồi.

### Recovery preview

**Tiêu đề:** So sánh phương án phục hồi  
**Mô tả:** Chưa có thay đổi nào được áp dụng. Hãy kiểm tra việc được giữ, việc bị dời và rủi ro còn lại.

### No feasible option

**Tiêu đề:** Chưa có phương án khả thi  
**Mô tả:** Ngay cả khi dời các việc ít ưu tiên, lịch hiện tại vẫn thiếu `{hours}` giờ. Kế hoạch cũ được giữ nguyên.

### Applied

**Tiêu đề:** Lịch mới đã được áp dụng  
**Mô tả:** Snapshot trước thay đổi đã được giữ trong lịch sử.

## 5. Q&A và liêm chính

### Insufficient sources

**Tiêu đề:** Chưa đủ nguồn để trả lời chắc chắn  
**Mô tả:** Kho học liệu hiện chưa xác minh được `{missing_part}`. Bạn có thể xem `{resource}` hoặc hỏi giảng viên trong office hour.

### Guided help

**Mô tả:** Mình không thể tạo toàn bộ đáp án để bạn nộp. Hãy gửi bước bạn đã thử; mình có thể giải thích khái niệm, chia cách làm thành từng bước hoặc dùng một ví dụ tương tự.

### Citation dispute

**Tiêu đề:** Đã ghi nhận phản ánh  
**Mô tả:** Đoạn nguồn này sẽ tạm thời không được dùng làm căn cứ chính trong khi chờ đối soát.  
**Phụ:** Mã phản ánh: `{dispute_id}`

## 6. Understanding

### Status labels

- Chưa đủ bằng chứng
- Còn nhầm lẫn
- Đang hình thành
- Đã thể hiện được

### Disclaimer

> Kết quả này hỗ trợ học tập và không phải điểm chính thức.

### Low confidence

**Tiêu đề:** Chưa đủ bằng chứng để kết luận  
**Mô tả:** Câu trả lời hiện `{reason}`. Bạn có thể trả lời thêm một câu hoặc gửi giảng viên xem.

## 7. Reflect

### Intro

**Tiêu đề:** Nhìn lại tuần bằng dữ kiện  
**Mô tả:** So sánh kế hoạch và thực tế để chọn một thay đổi nhỏ cho tuần sau. Đây không phải đánh giá về tính cách hay năng lực.

### Adjustment preview

**Nhãn:** Đề xuất cho tuần `{week_range}`  
**Mô tả:** Thay đổi này chưa được áp dụng cho đến khi bạn xác nhận.

## 8. Lỗi chung

### Connection

**Tiêu đề:** Chưa thể kết nối dịch vụ AI  
**Mô tả:** Dữ liệu bạn đã nhập vẫn được giữ lại và chưa có thay đổi nào được lưu.  
**CTA chính:** Thử lại  
**CTA phụ:** Tiếp tục với chức năng cơ bản

### Timeout

**Tiêu đề:** Tác vụ mất nhiều thời gian hơn dự kiến  
**Mô tả:** Hệ thống đã dừng an toàn để tránh ghi trùng. Bạn có thể thử lại với cùng dữ liệu.  
**Phụ:** Mã yêu cầu: `{request_id}`

### Stale data

**Banner:** Dữ liệu Canvas được đồng bộ lần cuối lúc `{timestamp}` và có thể chưa phản ánh thay đổi mới.  
**CTA:** Đồng bộ lại

### Permission

**Tiêu đề:** Bạn không có quyền mở trang này  
**Mô tả:** Tài khoản hiện tại không được cấp quyền cho khu vực này.  
**CTA:** Quay về tổng quan

## 9. Validation

| Trường hợp | Nội dung |
|---|---|
| Thiếu deadline | Chọn deadline để hệ thống kiểm tra tính khả thi. |
| Slot không hợp lệ | Giờ kết thúc phải sau giờ bắt đầu. |
| Slot trùng | Khung giờ này trùng với `{slot_name}`. |
| Không có availability | Thêm ít nhất một khung giờ rảnh trong tuần. |
| Câu trả lời quá ngắn | Viết thêm 2–3 câu để có đủ bằng chứng đánh giá. |
| Nội dung quá dài | Nội dung vượt quá `{limit}` ký tự. Hãy rút gọn trước khi gửi. |

