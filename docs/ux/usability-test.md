# PaceWise — Usability Test Plan

**Phiên bản:** 1.0  
**Phương pháp:** moderated usability test, think-aloud  
**Thời lượng:** 35–45 phút/người

## 1. Mục tiêu nghiên cứu

1. Sinh viên có hiểu Plan là bản xem trước trước khi xác nhận không?
2. Sinh viên có xác định được việc tiếp theo và lý do ưu tiên không?
3. Recover có giúp so sánh đánh đổi mà không gây quá tải nhận thức không?
4. Người dùng có phân biệt bằng chứng hiểu bài với điểm chính thức không?
5. Citation, lỗi và fallback có đủ rõ để người dùng biết hành động tiếp theo không?
6. Giảng viên có hiểu giới hạn riêng tư và hàng chờ không?

## 2. Người tham gia

### Sinh viên

- 5 người cho vòng đầu; tối thiểu 3 nếu thời gian hạn chế.
- Có sử dụng LMS/Canvas hoặc hệ thống tương tự.
- Trộn năm học, mức tự tin công nghệ và thói quen lập kế hoạch.
- Không tuyển chỉ thành viên nhóm phát triển.

### Giảng viên/cố vấn

- 2–3 người nếu Management Console nằm trong vòng test.
- Có kinh nghiệm giao assignment hoặc hỗ trợ sinh viên.

## 3. Thiết bị và dữ liệu

- Test desktop ở 1366 × 768 và mobile ở 360 × 800.
- Dùng dữ liệu fixture, không dùng điểm hoặc nội dung thật.
- Prototype phải có loading, error, infeasible và confirmation state.
- Ghi màn hình/âm thanh chỉ khi có đồng ý.
- Không thu API key, tài khoản Canvas thật hoặc dữ liệu nhạy cảm.

## 4. Kịch bản mở đầu

> Chúng tôi đang kiểm tra thiết kế, không kiểm tra khả năng của bạn. Hãy nói thành tiếng điều bạn đang nghĩ. Nếu có phần khó hiểu, đó là dữ liệu giúp chúng tôi cải thiện sản phẩm.

Không giải thích trước ý nghĩa Plan, Recover hoặc bốn trạng thái hiểu bài.

## 5. Nhiệm vụ sinh viên

### Task 1 — Tìm việc tiếp theo

**Bối cảnh:** Bạn có ba assignment trong tuần. Hãy tìm việc nên làm tiếp theo và giải thích vì sao nó được ưu tiên.

**Quan sát:** thời gian tìm, lý do người dùng đọc, có nhầm cảnh báo với deadline hay không.

### Task 2 — Tạo kế hoạch

**Bối cảnh:** Bạn có bài tiểu luận 2.000 từ nộp thứ Sáu tuần sau và sáu giờ rảnh. Hãy tạo kế hoạch nhưng chưa áp dụng ngay.

**Tiêu chí:** nhập đủ dữ liệu, đọc preview, nhận biết chưa lưu, tìm được giả định.

### Task 3 — Xử lý kế hoạch vô nghiệm

**Bối cảnh:** Khối lượng cần tám giờ nhưng lịch chỉ còn năm giờ. Hãy tìm một cách xử lý phù hợp.

**Tiêu chí:** nhận ra số giờ thiếu; không cố tìm nút lưu; chọn giảm phạm vi/thêm giờ/trao đổi.

### Task 4 — Phục hồi khi bị trễ

**Bối cảnh:** Một milestone mất lâu hơn dự kiến và deadline còn gần. Hãy so sánh các phương án, chọn một phương án và cho biết điều gì sẽ thay đổi.

**Tiêu chí:** hiểu năm tiêu chí, đọc diff, biết lịch chưa đổi trước xác nhận.

### Task 5 — Hỏi bài và kiểm tra nguồn

**Bối cảnh:** Hỏi một khái niệm trong môn, mở nguồn hỗ trợ và báo một citation sai.

**Tiêu chí:** mở đúng nguồn, không mất câu hỏi, tìm được report action, hiểu trạng thái xử lý.

### Task 6 — Kiểm tra mức hiểu

**Bối cảnh:** Trả lời một câu mở, xem kết quả và nói kết quả này có phải điểm chính thức không.

**Tiêu chí:** đọc đúng trạng thái, độ tin cậy, evidence và hành động tiếp.

### Task 7 — Lỗi kết nối

**Bối cảnh:** Dịch vụ AI không phản hồi. Hãy cho biết dữ liệu đã được lưu chưa và bạn sẽ làm gì tiếp.

**Tiêu chí:** hiểu trạng thái dữ liệu; tìm được retry/fallback.

## 6. Nhiệm vụ giảng viên

1. Tìm đơn vị kiến thức có xu hướng cần hỗ trợ.
2. Giải thích vì sao một nhóm dưới năm người không hiển thị.
3. Duyệt một rubric hoặc trả lại kèm ghi chú.
4. Xử lý một ca độ tin cậy thấp.
5. Chuẩn bị hỗ trợ cá nhân nhưng dừng trước khi xác nhận.

## 7. Câu hỏi sau mỗi task

- Bạn kỳ vọng điều gì xảy ra sau khi bấm nút này?
- Bạn nghĩ thay đổi đã được lưu chưa? Vì sao?
- Thông tin nào giúp bạn quyết định?
- Phần nào khiến bạn do dự?
- Bạn sẽ làm gì tiếp theo?

Không hỏi câu dẫn như “Nhãn bản xem trước có rõ không?”.

## 8. Câu hỏi cuối phiên

- Phần nào hữu ích nhất và ít hữu ích nhất?
- Có lúc nào bạn cảm thấy AI tự quyết định thay bạn không?
- Bạn có tin citation và kết quả hiểu bài không? Vì sao?
- Có thông tin nào bạn không muốn giảng viên nhìn thấy?
- Nếu chỉ thay đổi một điều, bạn muốn thay đổi gì?
- Chấm mức dễ sử dụng từ 1–5 và giải thích.

## 9. Chỉ số

| Chỉ số | Cách tính | Mục tiêu |
|---|---|---:|
| Task completion | Hoàn thành đúng/ tổng người thử | ≥80% |
| Unassisted completion | Hoàn thành không cần moderator | ≥70% |
| Critical error | Lưu/hiểu sai thay đổi quan trọng | ≤5% |
| Time on task | Median theo từng task | Dùng so sánh vòng sau |
| Confidence | Tự đánh giá 1–5 | ≥4 |
| Preview comprehension | Biết thay đổi chưa lưu | ≥80% |
| Assessment comprehension | Biết kết quả không phải điểm | ≥80% |

## 10. Severity

| Mức | Định nghĩa | Hành động |
|---|---|---|
| S0 Blocker | Không thể hoàn thành hoặc gây ghi sai dữ liệu | Sửa trước vòng test tiếp theo |
| S1 Critical | Nhiều người hiểu sai confirmation/privacy | Sửa trước handoff frontend |
| S2 Major | Chậm, do dự hoặc cần hỗ trợ | Ưu tiên sprint hiện tại |
| S3 Minor | Câu chữ/hình thức gây khó nhẹ | Đưa backlog |

## 11. Mẫu ghi nhận

| Participant | Task | Outcome | Time | Error/quote | Severity | Recommendation |
|---|---|---|---:|---|---|---|
| P01 | T2 Plan | Success/Partial/Fail |  |  |  |  |

## 12. Báo cáo sau test

Báo cáo cần có:

- Người tham gia và giới hạn mẫu.
- Completion rate theo task.
- Năm vấn đề ưu tiên kèm bằng chứng.
- Ảnh màn hình/vị trí gây lỗi.
- Khuyến nghị cụ thể và chủ sở hữu.
- Quyết định nào đã thay đổi trong wireframe/microcopy.
- Các vấn đề chưa xử lý và lý do.

