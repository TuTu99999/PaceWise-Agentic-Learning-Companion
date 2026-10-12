# PaceWise — UX Acceptance Criteria

**Phiên bản:** 1.0  
**Mục đích:** tiêu chí bàn giao UX cho UI/frontend và UAT

## 1. Tiêu chí toàn cục

- [ ] Người dùng luôn biết mình đang ở vai trò sinh viên hay giảng viên.
- [ ] Mọi màn hình có idle/loading/success/empty/error phù hợp.
- [ ] Hành động ghi dữ liệu quan trọng có preview và confirmation.
- [ ] UI nói rõ thay đổi đã lưu hay chưa.
- [ ] Không hiển thị stack trace, prompt nội bộ, API key hoặc lỗi kỹ thuật thô.
- [ ] Không dùng màu làm tín hiệu duy nhất.
- [ ] Keyboard navigation và focus order hợp lý.
- [ ] Form có label, lỗi sát trường và error summary.
- [ ] Responsive được kiểm tra ở 360 px, 768 px và desktop.
- [ ] Ngày giờ hiển thị timezone và deadline cụ thể.
- [ ] Thuật ngữ khớp PRD; không lộ tên node/agent kỹ thuật.

## 2. Đăng nhập và dữ liệu nguồn

### Given/When/Then

- **Given** người dùng có vai trò sinh viên, **when** mở route giảng viên, **then** hệ thống trả 403, không lộ dữ liệu và có đường quay về.
- **Given** chưa có dữ liệu tuần, **when** mở dashboard, **then** hiển thị empty state với đúng một CTA chính.
- **Given** Canvas không truy cập được, **when** có snapshot cũ, **then** hiển thị timestamp, nhãn dữ liệu cũ và nút đồng bộ lại.
- **Given** nhóm giảng viên có `n < 5`, **when** mở dashboard lớp, **then** số liệu cá nhân/tổng hợp bị ẩn và có giải thích quyền riêng tư.

## 3. Plan

- [ ] Chọn được tuần, assignment, mục tiêu và mức ưu tiên.
- [ ] Khai báo được availability và unavailable slots.
- [ ] Slot trùng hoặc sai thời gian được báo trước khi gọi AI.
- [ ] Mỗi milestone có tên, đầu ra, thời lượng, dependency và nguồn assignment.
- [ ] Tổng thời lượng và quỹ thời gian được hiển thị cùng đơn vị.
- [ ] Deadline tương đối được chuyển thành ngày cụ thể hoặc yêu cầu xác nhận.
- [ ] Preview có nhãn “chưa lưu”.
- [ ] Người dùng sửa một mốc mà không mất các mốc khác.
- [ ] Chỉ bấm “Xác nhận và lưu” mới ghi kế hoạch.
- [ ] Trường hợp vô nghiệm hiển thị giờ thiếu và không có nút lưu.
- [ ] Timeout giữ nguyên input và cho retry/fallback.

## 4. Tracking

- [ ] Dashboard hiển thị việc tiếp theo, thời lượng, deadline và lý do ưu tiên.
- [ ] Có thể bắt đầu/kết thúc phiên hoặc nhập thủ công.
- [ ] Không cho chạy hai timer xung đột.
- [ ] Sau cập nhật, tiến độ/sai lệch/slack được phản hồi trong mục tiêu hiệu năng của PRD.
- [ ] Cảnh báo nêu dữ kiện, ảnh hưởng và lựa chọn.
- [ ] Người dùng có thể đánh dấu dữ liệu sai và sửa lại.
- [ ] Bỏ qua cảnh báo không tự thay đổi lịch.

## 5. Q&A

- [ ] Câu trả lời grounded có citation ngay cạnh luận điểm.
- [ ] Citation mở đúng tài liệu và vị trí nguồn.
- [ ] Quay lại từ nguồn không làm mất câu hỏi đang nhập.
- [ ] Thiếu nguồn dẫn tới abstain, không bịa citation.
- [ ] Yêu cầu làm hộ không tạo đáp án/code hoàn chỉnh để nộp.
- [ ] Integrity redirect có ít nhất một hành động học thay thế.
- [ ] Báo citation sai tạo xác nhận và mã phản ánh.
- [ ] Citation bị phản ánh không tiếp tục làm căn cứ chính cho đến khi review.

## 6. Understanding

- [ ] Chỉ sử dụng bốn trạng thái bằng chứng chuẩn.
- [ ] Không hiển thị điểm số, letter grade hoặc ghi gradebook.
- [ ] Kết quả có đủ bốn khía cạnh rubric.
- [ ] Mỗi nhận xét quan trọng có evidence quote từ câu trả lời.
- [ ] Có độ tin cậy, giới hạn và đúng một hành động tiếp theo.
- [ ] Câu trả lời quá ngắn/mâu thuẫn dẫn tới “chưa đủ bằng chứng”.
- [ ] Ca độ tin cậy thấp có thể gửi hàng chờ giảng viên.
- [ ] Luôn hiển thị disclaimer “không phải điểm chính thức”.

## 7. Recover

- [ ] Chỉ hiển thị phương án đã qua validation ràng buộc.
- [ ] Có 2–3 phương án khi đủ nghiệm; nếu không đủ phải nói rõ.
- [ ] Mỗi phương án có đủ năm tiêu chí trade-off.
- [ ] Không tự giả định availability mà không đánh dấu.
- [ ] So sánh dùng cùng cấu trúc và đơn vị.
- [ ] Diff chỉ rõ added/moved/removed bằng chữ và màu/icon.
- [ ] Kế hoạch cũ không đổi trước confirmation cuối.
- [ ] Sau xác nhận, snapshot cũ còn trong audit.
- [ ] Người dùng có thể bỏ qua Recover an toàn.

## 8. Reflect

- [ ] Tóm tắt dựa trên dữ kiện kế hoạch–thực tế.
- [ ] Không phán xét tính cách hoặc năng lực.
- [ ] Form có tối đa ba câu phản tư.
- [ ] Chỉ đề xuất một điều chỉnh cụ thể, đo được.
- [ ] Hiển thị ngày/tuần có hiệu lực.
- [ ] “Chỉ lưu phản tư” không làm thay đổi kế hoạch tuần sau.
- [ ] Chỉ xác nhận mới áp dụng điều chỉnh.

## 9. Management Console

- [ ] Chỉ hiển thị xu hướng tổng hợp khi `n ≥ 5`.
- [ ] Không hiển thị chat, câu trả lời hoặc phản tư thô.
- [ ] Rubric/câu hỏi có trạng thái draft, review, approved/rejected.
- [ ] Hàng chờ có evidence, confidence, giới hạn và lý do.
- [ ] Hỗ trợ cá nhân có preview đối tượng, nội dung và căn cứ.
- [ ] Mọi quyết định duyệt/hỗ trợ được audit.

## 10. Error, reliability và privacy

- [ ] Error nói rõ tác vụ nào chưa hoàn tất.
- [ ] Error nói rõ input còn được giữ và dữ liệu đã lưu hay chưa.
- [ ] Có request ID cho lỗi cần hỗ trợ.
- [ ] Retry dùng idempotency key cho hành động ghi dữ liệu.
- [ ] Không có vòng loading vô hạn; timeout mặc định có trạng thái kết thúc.
- [ ] Analytics không chứa nội dung học tập thô.
- [ ] URL, log và thông báo không chứa dữ liệu nhạy cảm.

## 11. Accessibility

- [ ] Tương phản đạt WCAG 2.1 AA.
- [ ] Touch target khoảng 44 × 44 px trở lên.
- [ ] Screen reader nhận được label, status và error.
- [ ] Loading/cập nhật động dùng `aria-live` phù hợp.
- [ ] Modal giữ focus, đóng bằng Escape và trả focus về trigger.
- [ ] Bảng/biểu đồ có dữ liệu tương đương không phụ thuộc hình ảnh.
- [ ] Trạng thái focus, disabled, selected và error nhìn thấy rõ.
- [ ] `prefers-reduced-motion` được tôn trọng.

## 12. Definition of Done cho bàn giao UX

- [ ] Persona và user needs đã được PO/BA review.
- [ ] Sitemap và user flow không mâu thuẫn PRD.
- [ ] Wireframe/UI bao phủ toàn bộ trạng thái trong `screen-states.md`.
- [ ] Microcopy đã được dùng trong prototype thay vì lorem ipsum.
- [ ] Prototype có ba happy path: Plan, Recover, Q&A/Check.
- [ ] Có ít nhất một error path và một infeasible path có thể test.
- [ ] Usability test đã thực hiện với tối thiểu 3 sinh viên.
- [ ] Vấn đề S0/S1 đã được sửa hoặc có quyết định chấp nhận rủi ro.
- [ ] UI designer nhận đủ component/state/content specification.
- [ ] Frontend và backend thống nhất API contract cho status, confirmation, citations và errors.

