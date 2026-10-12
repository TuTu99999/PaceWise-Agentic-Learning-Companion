# Tách nhiệm vụ quá hạn khỏi kế hoạch tương lai — 10/10/2026

## Nguyên nhân và sửa đổi

UI Plan vẫn chọn nhiệm vụ từ mốc demo 05/10. Scheduler bỏ ca quá khứ nhưng vẫn giữ tổng công việc của nhiệm vụ đã hết hạn, dẫn tới yêu cầu thêm giờ trước một deadline không còn khả dụng.

Đã sửa:

- Plan dùng ngày/giờ thật tại Asia/Ho_Chi_Minh, cập nhật mỗi phút và khi quay lại tab. Kéo thả, chọn nhiệm vụ, horizon và pin lịch sử không dùng mốc demo cố định nữa.
- Backend phân loại assignment đang mở thành còn hạn và quá hạn theo **instant**; date-only vẫn có hạn cuối ngày địa phương. Việc đã nộp/graded/excused không được xếp lại như việc còn mở.
- Nhiệm vụ quá hạn không sinh milestone, planning target, đề xuất estimate, goal hoặc capacity shortfall cho lịch tương lai. Explicit milestone của task bị loại không được gán nhầm sang task còn hạn duy nhất.
- Input phân rã/goal của Plan gửi model chỉ chứa assignment còn hạn. Lịch sử Do/Reflect và Knowledge State không bị xóa hay giảm.
- Draft mới giữ `expiredTasks` dạng `overdue_unresolved`; lịch quá khứ vẫn có thể hiện read-only. **Quá hạn không đồng nghĩa hoàn thành**.
- Draft cũ còn chứa công việc hết hạn được đánh dấu stale và yêu cầu phân tích lại; không chỉ ẩn lỗi rồi tự coi lịch khả thi. UI không lặp “thiếu 9 giờ capacity” từ snapshot cũ như một kết luận về tương lai.
- Tổng ca/giờ trên lịch tách khỏi lịch sử đã qua; bản đang áp dụng vẫn giữ nguyên tới khi sinh viên xác nhận draft mới.

Regression còn phát hiện serializer simulator trả datetime UTC thiếu offset sau khi SQLite lưu. Đã chuẩn hóa `_iso` của learning/integration API và planner payload về UTC có offset. Không nới validator deadline để test pass. Test override thực kiểm tra `+00:00` được giữ và một hạn 13:17 địa phương vẫn còn hạn tại 10:00.

Lỗi dependency của một bài **còn hạn** vẫn là lỗi thật và phải xử lý; việc tách overdue không bỏ qua dependency, overlap hoặc quality gate.

## Rút thông tin từ lịch sử như thế nào?

Đường cá nhân hóa đã có trong `plan_intelligence.py`, `study_rhythm.py` và learner memory:

| Dữ liệu | Dùng được cho | Giới hạn |
| --- | --- | --- |
| Planned/actual time của timer có provenance | Ước lượng khối lượng công việc | Estimate cần tối thiểu 3 phiên distinct cùng task/loại hoạt động, baseline readiness và nhịp tương đồng; loại phiên gián đoạn, không đủ completion hoặc gap không quan sát |
| Reflect báo phiên quá dài/mệt lặp lại | Đề xuất thử nhịp ngắn hơn trong đúng context | Tối thiểu 3 phiên phù hợp; bước thử nhỏ, giữ tổng công việc và yêu cầu xác nhận |
| Assessment evidence có ID | Mức thể hiện, misconception, prerequisite, retention khi đã test | Không lấy time, deadline qua, quiz score hoặc self-report làm bằng chứng hiểu bài |
| Bỏ lỡ ca/bận đột xuất | Reflect nguyên nhân và kiểm tra capacity | Không tự tăng estimate, giảm Knowledge State hoặc kết luận lười/không hiểu |

Không có đủ evidence thì giữ preference và estimate nền, báo bất định. Code hiện không chứng minh mỗi người có một “thời lượng tối ưu” hoặc một “khung giờ học hiệu quả nhất”. Muốn suy ra các điều đó cần pilot và so sánh hoạt động tương đồng. Học bù sau deadline là một mục tiêu ôn/học mới hoặc deadline mới chính thức từ LMS, không tự sửa deadline cũ; không thêm tính năng học bù mới trong bản sửa này.

## Evaluation

- Backend: **680 passed**; [JUnit](../evals/reports/expired-planning-backend-2026-10-10.xml).
- Frontend: **316 passed**; [JUnit](../evals/reports/expired-planning-frontend-2026-10-10.xml).
- Simulator độc lập: **80 passed**; [JUnit](../evals/reports/expired-planning-simulator-2026-10-10.xml).
- Browser expired: **2 passed**, mobile 390×844 và desktop 1366×900. Review lại snapshot cũ, loại cả deadline hết hạn trong ngày, chỉ gửi task còn hạn cho Plan, tạo draft mới và vẫn chờ xác nhận. [Results](../evals/reports/expired-planning-ui-2026-10-10/results.json).
- Browser partial confirmation regression: **9 passed**, vẫn vào Do sau xác nhận phần an toàn, không bỏ qua ca vượt deadline.
- Production TypeScript/Vite build: PASS.

Test service còn kiểm tra không mutate input/LMS submission, giữ ca lịch sử, không mất công việc overdue, không gắn milestone quá hạn sang bài mới, và loại overdue khỏi uncovered future work.

Browser chạy fixture; không dùng tài khoản người học thật, không gọi LLM thật. Các test này chứng minh bộ lọc và workflow kỹ thuật, không chứng minh hiệu quả cá nhân hóa, cải thiện learning outcome hoặc tải 1.000 người.

## Sau cập nhật

Backend, frontend và LMS simulator Docker local đã rebuild/recreate; không reset database. Cả ba healthy; kiểm tra backend `/health`, frontend `/app.html` và simulator `/health` đều HTTP 200. Người dùng tải lại trang, đồng bộ LMS nếu cần, rồi bấm **AI phân tích lại** một lần để thay kết quả capacity cũ bằng draft theo thời gian hiện tại.
