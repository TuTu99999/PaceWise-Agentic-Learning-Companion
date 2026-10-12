# PaceWise — Screen States

**Phiên bản:** 1.0  
**Mục tiêu:** định nghĩa trạng thái bắt buộc để UI và frontend không chỉ thiết kế happy path

## 1. Mô hình trạng thái chung

| Trạng thái | Ý nghĩa | UI bắt buộc |
|---|---|---|
| `idle` | Chưa bắt đầu tác vụ | Form và CTA chính |
| `validating` | Kiểm tra dữ liệu | Giữ form, chỉ ra trường đang kiểm tra |
| `queued` | Server đã nhận tác vụ | Xác nhận đã nhận, cho phép rời màn hình |
| `processing` | Đang xử lý | Mô tả bước hiện tại, elapsed time, nút hủy nếu an toàn |
| `needs_confirmation` | Có thay đổi chờ duyệt | Preview/diff, nguồn, giả định, rủi ro, CTA xác nhận |
| `success` | Hoàn tất | Kết quả, thời điểm lưu và hành động tiếp theo |
| `empty` | Chưa có dữ liệu | Lý do và đúng một CTA chính |
| `abstained` | Không đủ căn cứ để kết luận | Phần thiếu, giới hạn và cách bổ sung |
| `stale` | Dữ liệu nguồn đã cũ | Timestamp, tác động và nút đồng bộ |
| `failed` | Tác vụ thất bại | Lỗi thân thiện, dữ liệu có được lưu không, retry/fallback |
| `forbidden` | Sai quyền | Không lộ dữ liệu, đường quay về đúng vai trò |

## 2. Ma trận trạng thái theo màn hình

| ID | Màn hình | Trạng thái bắt buộc |
|---|---|---|
| C0 | Đăng nhập/chọn vai trò | idle, validating, failed, forbidden |
| S0 | Chưa có dữ liệu tuần | empty, processing, failed |
| S1 | Tổng quan tuần | success, stale, empty, failed |
| S2 | Mục tiêu và quỹ thời gian | idle, validating, invalid, conflict |
| S3 | Tạo kế hoạch | queued, processing, timeout, cancelled |
| S4 | Preview Plan | feasible, overloaded, infeasible, needs_confirmation |
| S5 | Phiên học/tiến độ | idle, running, paused, saved, failed |
| S6 | Cảnh báo | new, acknowledged, disputed, resolved |
| S7 | Recover | processing, options, infeasible, needs_confirmation, success |
| S8 | Q&A | idle, processing, grounded, insufficient, failed |
| S9 | Integrity redirect | blocked, guided_help |
| S10 | Check | question, answering, submitted, processing |
| S11 | Evidence | confident, low_confidence, abstained, teacher_queue |
| S12 | Reflect | draft, needs_confirmation, saved, applied |
| I0 | Dashboard giảng viên | empty, privacy_threshold |
| I1 | Tổng quan lớp | success, stale, filtered |
| I2 | Hàng chờ | empty, pending, in_review, resolved |
| I3 | Hỗ trợ | preview, needs_confirmation, success, failed |

## 3. Plan

### Form chưa hợp lệ

- Hiển thị lỗi sát trường và summary đầu form.
- Không xóa dữ liệu đã nhập.
- Focus chuyển tới lỗi đầu tiên sau submit.
- Ví dụ: thiếu deadline, slot kết thúc trước lúc bắt đầu, hai slot trùng nhau.

### Processing

- Nội dung: “Đang chia nhiệm vụ và kiểm tra deadline…”.
- Không dùng progress phần trăm giả; có thể dùng bước `1/3`, `2/3`, `3/3` nếu backend cung cấp.
- Sau 30 giây chuyển timeout an toàn.

### Feasible preview

- Nhãn nổi bật: **Bản xem trước — chưa lưu**.
- Hiển thị tổng giờ dùng/có, xung đột, slack, giả định.
- CTA: “Chỉnh sửa”, “Hủy”, “Xác nhận và lưu”.

### Infeasible

- Nêu số giờ thiếu và deadline bị ảnh hưởng.
- CTA: “Giảm phạm vi”, “Thêm thời gian”, “Xem mẫu trao đổi”.
- Không có nút “Xác nhận và lưu”.

## 4. Tracking và cảnh báo

### Timer đang chạy

- Hiển thị nhiệm vụ, thời lượng đã trôi và nút kết thúc.
- Nếu đóng trang, xác nhận timer vẫn tiếp tục hay bị dừng.
- Không tạo hai timer đồng thời cho cùng người dùng.

### Risk signal

- Luôn có ba phần: dữ kiện, ảnh hưởng, lựa chọn.
- Cho phép “Dữ liệu chưa đúng” để sửa evidence.
- Không dùng animation đỏ nhấp nháy hoặc ngôn ngữ gây hoảng sợ.

## 5. Q&A

### Grounded

- Citation nằm ngay sau luận điểm liên quan.
- Citation là control có label mô tả tài liệu/trang/đoạn.
- Có hành động “Báo nguồn sai”.

### Insufficient sources

- Nêu phần nào chưa xác minh được.
- Gợi ý từ khóa, tài liệu hoặc office hour.
- Không tạo citation giả hoặc biến kiến thức ngoài nguồn thành kết luận chắc chắn.

### Integrity redirect

- Không dùng thông điệp trừng phạt.
- Giải thích ngắn ranh giới.
- Đưa ra hành động thay thế: gửi cách làm thử, xem khái niệm, dùng ví dụ tương tự.

## 6. Understanding

### Confident result

- Chỉ dùng bốn trạng thái chuẩn.
- Có độ tin cậy, bốn khía cạnh, evidence quote, giới hạn và bước tiếp.
- Hiển thị câu “Đây không phải điểm chính thức”.

### Abstained/low confidence

- Tiêu đề: “Chưa đủ bằng chứng để kết luận”.
- Nêu lý do: câu quá ngắn, mâu thuẫn hoặc ngoài rubric.
- CTA: “Trả lời thêm” hoặc “Gửi giảng viên xem”.

## 7. Recover

### Options

- So sánh cùng năm tiêu chí và cùng đơn vị.
- Một phương án có thể được gợi ý nhưng không preselect nút xác nhận.
- Mọi giả định availability phải được đánh dấu và cho sửa.

### Diff confirmation

- Added/moved/removed phải có nhãn chữ, không chỉ màu.
- Hiện kế hoạch cũ và mới hoặc diff dễ đọc trên mobile.
- Nút hủy không đặt sát CTA xác nhận nguy cơ cao.

### No solution

- Nói thẳng không còn lịch khả thi.
- Giữ nguyên kế hoạch hiện tại.
- Cung cấp cách giảm phạm vi hoặc mẫu trao đổi với giảng viên.

## 8. Reflect

- Draft không tự áp dụng tuần sau.
- Đề xuất chỉ chứa một thay đổi đo được.
- `effective_week` hiển thị bằng ngày cụ thể.
- Cho phép “Chỉ lưu phản tư” không kèm điều chỉnh.
- Không dùng đánh giá tính cách hoặc năng lực.

## 9. Error và offline

Mọi error state phải trả lời:

1. Điều gì chưa hoàn tất?
2. Dữ liệu người dùng đã nhập có còn không?
3. Có thay đổi nào đã được lưu không?
4. Người dùng có thể làm gì tiếp theo?
5. `request_id` nào dùng khi cần hỗ trợ?

Không hiển thị stack trace, API key, prompt nội bộ hoặc tên exception kỹ thuật.

## 10. Responsive và accessibility states

- 360 px: bảng chuyển thành card hoặc danh sách định nghĩa, không cuộn ngang cho hành động chính.
- 768 px: side panel có thể thay modal toàn màn hình.
- Desktop: giữ chiều dài dòng nội dung khoảng 60–80 ký tự.
- Focus, hover, pressed, disabled và error phải được thiết kế cho mọi interactive component.
- Skeleton chỉ dùng khi cấu trúc đã biết; không dùng skeleton thay cho tác vụ AI dài.
- `prefers-reduced-motion` loại animation không thiết yếu.

