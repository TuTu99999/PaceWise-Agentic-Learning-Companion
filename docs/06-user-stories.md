# PaceWise — User Stories

**Phiên bản:** 1.0 · **Đội:** P-008 · **Cập nhật:** 30/09/2026
**Phạm vi:** MVP cho sinh viên và giảng viên, tích hợp LMS Simulator/Canvas theo chu trình **Plan → Do → Check → Recover → Reflect**.

## 1. Mục đích

Tài liệu này chuyển PRD thành các lát cắt chức năng có thể phát triển, kiểm thử và nghiệm thu. Mỗi user story mô tả giá trị cho người dùng, không mô tả riêng một công nghệ hoặc một màn hình.

Quy ước ưu tiên:

- **P0:** bắt buộc để MVP chạy end-to-end.
- **P1:** cần cho pilot tốt nhưng có thể phát hành sau P0.
- **P2:** hướng mở rộng sau khi pilot chứng minh hiệu quả.

## 2. Personas

| Persona | Nhu cầu chính | Rủi ro cần tránh |
|---|---|---|
| Sinh viên | Tổng hợp deadline nhiều môn, lập kế hoạch khả thi, nhận cảnh báo sớm, phục hồi kế hoạch và biết phần kiến thức cần ôn | Kế hoạch quá tải, AI làm hộ bài, kết luận hiểu bài thiếu căn cứ, thay đổi lịch khi chưa xác nhận |
| Giảng viên/cố vấn | Quan sát xu hướng lớp, duyệt rubric và xử lý các trường hợp AI không chắc chắn | Lộ dữ liệu cá nhân, dùng AI như công cụ giám sát hoặc chấm điểm chính thức |

## 3. User story map

| Giai đoạn | Sinh viên | Giảng viên/cố vấn |
|---|---|---|
| Khởi tạo | Đăng nhập, chọn môn, đồng bộ LMS, khai báo thời gian | Đăng nhập, chọn lớp, kiểm tra dữ liệu môn |
| Plan | Xem deadline, tạo và xác nhận kế hoạch tuần | Duyệt mục tiêu/rubric dùng cho đánh giá |
| Do | Xem việc tiếp theo, ghi nhận thời gian, hỏi đáp có nguồn | Xem xu hướng tiến độ tổng hợp |
| Check | Làm kiểm tra nhanh, nhận bằng chứng và mức tin cậy | Duyệt ca đánh giá không chắc chắn |
| Recover | Nhận cảnh báo, so sánh phương án, xác nhận lịch mới | Hỗ trợ ca không còn phương án khả thi |
| Reflect | Phản tư cuối tuần, xác nhận điều chỉnh cho tuần sau | Xem xu hướng vướng mắc theo chủ đề |

## 4. User stories của sinh viên

### US-STU-01 — Đăng nhập và nhận đúng quyền

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn đăng nhập và chỉ truy cập dữ liệu học tập của mình để thông tin cá nhân không bị lộ cho người khác.

**Acceptance criteria:**

1. **Given** tài khoản sinh viên hợp lệ, **when** đăng nhập thành công, **then** hệ thống tạo session phía server và đưa người dùng tới dashboard sinh viên.
2. **Given** sinh viên đã đăng nhập, **when** thay đổi `user_id`, `course_id` hoặc role trong request, **then** backend vẫn dùng danh tính trong session và từ chối tài nguyên không có quyền.
3. **Given** session hết hạn hoặc đã bị thu hồi, **when** gọi API bảo vệ, **then** hệ thống trả `401` và yêu cầu đăng nhập lại.
4. Không ghi mật khẩu, token hoặc cookie vào log.

### US-STU-02 — Xem dữ liệu nhiều môn từ LMS

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn xem course, assignment, deadline, module và submission từ LMS để không phải tổng hợp thủ công.

**Acceptance criteria:**

1. Hiển thị được danh sách môn mà sinh viên đã enrollment.
2. Khi chuyển môn, assignment, module, tài liệu và trạng thái nộp phải thuộc đúng môn được chọn.
3. Mỗi lần đồng bộ hiển thị nguồn dữ liệu và thời điểm cập nhật gần nhất.
4. Khi LMS lỗi, dùng snapshot gần nhất nếu có và gắn nhãn dữ liệu cũ; không tự đoán deadline bị thiếu.
5. Không để dữ liệu của hai trường hoặc hai course trùng mã bị trộn lẫn.

### US-STU-03 — Khai báo quỹ thời gian và lịch bận

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn khai báo thời gian có thể học để kế hoạch không vượt quá khả năng thực tế.

**Acceptance criteria:**

1. Cho phép thiết lập khung giờ có thể học theo từng ngày.
2. Cho phép nhập lịch bận nội bộ hoặc đọc busy/free từ Google Calendar sau khi cấp quyền.
3. Không đọc tiêu đề hoặc nội dung sự kiện Google khi chỉ cần busy/free.
4. Slot học không được chồng lên khoảng bận hoặc nằm ngoài quỹ thời gian đã xác nhận.
5. Nếu không kết nối Google, chức năng lập kế hoạch nội bộ vẫn hoạt động bình thường.
6. Khi thêm hoặc kéo dài khoảng bận trùng study block đã lưu, hệ thống tạo cảnh báo Recover nhưng không tự đổi lịch.
7. Khi xóa hoặc rút ngắn khoảng bận, hệ thống báo capacity mới nhưng không tự nhồi thêm việc.
8. Sinh viên không phải nhập lý do; thay đổi lịch cá nhân không làm thay đổi deadline hoặc trạng thái học vụ trong LMS.

### US-STU-04 — Tạo kế hoạch tuần khả thi

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn hệ thống chia nhiệm vụ thành milestone và xếp lịch theo deadline để biết nên làm gì tiếp theo.

**Acceptance criteria:**

1. Mỗi milestone có đầu ra, thời lượng dự kiến, deadline nội bộ, course và assignment nguồn.
2. Backend là nguồn duy nhất tạo lịch chính thức; frontend chỉ hiển thị kết quả trả về.
3. Tổng thời lượng không vượt quỹ thời gian và mỗi milestone phải kết thúc trước deadline tương ứng.
4. Deadline, prerequisite, trọng số assignment group và trạng thái module được dùng khi tính ưu tiên nếu LMS cung cấp.
5. Nếu bài toán vô nghiệm, hệ thống nêu số giờ thiếu và deadline xung đột thay vì tạo lịch giả.

### US-STU-05 — Xem trước và xác nhận kế hoạch

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn xem và chỉnh kế hoạch trước khi lưu để AI không tự ý thay đổi lịch của tôi.

**Acceptance criteria:**

1. Bản xem trước hiển thị study block, lý do ưu tiên, giả định và cảnh báo xung đột.
2. Kế hoạch chỉ được ghi vào database sau khi sinh viên xác nhận.
3. Khi hủy, kế hoạch hiện tại không thay đổi.
4. Việc tạo, sửa, xác nhận hoặc hủy được ghi audit log nhưng không lưu dữ liệu nhạy cảm thừa.

### US-STU-06 — Đồng bộ kế hoạch với lịch ngoài

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn đưa study block đã xác nhận vào ứng dụng lịch để theo dõi cùng lịch cá nhân.

**Acceptance criteria:**

1. Có thể tải file `.ics` mà không cần OAuth.
2. Khi kết nối Google Calendar, màn hình phải hiển thị rõ tài khoản Google đang sử dụng; tài khoản này không bắt buộc trùng email trường.
3. Trước khi tạo sự kiện Google, hiển thị danh sách study block và yêu cầu xác nhận.
4. Việc gửi lại cùng một yêu cầu không tạo sự kiện trùng lặp.
5. Người dùng có thể ngắt kết nối và token bị thu hồi/xóa an toàn.

### US-STU-07 — Theo dõi tiến độ thực tế

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn ghi thời gian và trạng thái thực tế để biết kế hoạch đang lệch bao nhiêu.

**Acceptance criteria:**

1. Cho phép bắt đầu/kết thúc phiên học hoặc nhập thời gian thực tế.
2. Cập nhật được trạng thái chưa làm, đang làm, hoàn thành hoặc bị chặn.
3. Sau cập nhật, backend tính lại sai số thời gian, phần trăm hoàn thành và slack trước deadline.
4. Dữ liệu vẫn còn sau khi đổi trình duyệt hoặc đăng nhập lại.
5. Cập nhật lặp lại với cùng idempotency key không tạo bản ghi trùng.

### US-STU-08 — Nhận cảnh báo sớm

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn được cảnh báo khi kế hoạch không còn đủ để đáp ứng deadline để có thời gian xử lý trước khi quá muộn.

**Acceptance criteria:**

1. Cảnh báo dựa trên dữ liệu xác định như slack, thời gian thực tế, prerequisite và khối lượng còn lại.
2. Mỗi cảnh báo nêu rõ nhiệm vụ bị ảnh hưởng, nguyên nhân, deadline và mức độ rủi ro.
3. Rủi ro đã hết phải được đóng hoặc cập nhật, không tiếp tục xuất hiện do state cũ.
4. Nếu dữ liệu thiếu hoặc cũ, hệ thống phải hiển thị giới hạn thay vì kết luận chắc chắn.

### US-STU-09 — Phục hồi kế hoạch

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn so sánh các phương án phục hồi để bảo vệ deadline quan trọng khi một nhiệm vụ kéo dài hơn dự kiến.

**Acceptance criteria:**

1. Trả về 2–3 phương án hợp lệ nếu tồn tại, kèm việc giữ, việc dời, deadline được bảo vệ và rủi ro còn lại.
2. Mỗi phương án phải đi qua deterministic constraint validator.
3. Nếu không còn phương án khả thi, hệ thống nói rõ và gợi ý trao đổi với giảng viên.
4. Hiển thị diff trước–sau và chỉ áp dụng sau khi sinh viên xác nhận.
5. Snapshot kế hoạch trước khi thay đổi được giữ để audit hoặc khôi phục.
6. Recover dùng cùng dữ liệu đa môn đang hiển thị trong tab Kế hoạch: LMS cố định, study block và hard constraint cá nhân.
7. Study block bị xung đột không còn được tính là capacity hợp lệ; deadline LMS vẫn giữ nguyên.

### US-STU-10 — Hỏi đáp dựa trên tài liệu môn học

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn hỏi nội dung môn học và nhận câu trả lời có nguồn để có thể tự kiểm chứng.

**Acceptance criteria:**

1. Retrieval chỉ tìm tài liệu mà sinh viên có quyền trong đúng institution/course/resource version.
2. Câu trả lời có citation tới tài liệu và đoạn nguồn liên quan.
3. Khi nguồn không đủ hoặc điểm retrieval dưới ngưỡng cấu hình, hệ thống từ chối kết luận chắc chắn.
4. Prompt instruction nằm trong tài liệu không được phép thay đổi system policy.
5. Người dùng có thể báo citation sai; báo cáo tạo review case bền vững cho giảng viên.

### US-STU-11 — Được hỗ trợ mà không bị làm hộ bài

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn nhận gợi ý từng bước để học được cách giải mà vẫn bảo đảm liêm chính học thuật.

**Acceptance criteria:**

1. Safety pipeline gồm rule nhanh, classifier và output policy.
2. Yêu cầu tạo đáp án hoàn chỉnh cho bài tính điểm bị chặn hoặc chuyển thành gợi ý học tập.
3. Câu hỏi khái niệm hợp lệ không bị chặn chỉ vì chứa từ khóa giống bài tập.
4. Output cuối được kiểm tra lại trước khi trả cho người dùng.
5. Ca mơ hồ được chuyển sang chế độ an toàn hoặc review thay vì tự tin trả lời.

### US-STU-12 — Kiểm tra mức độ hiểu bài

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn làm kiểm tra nhanh và biết điểm mạnh/yếu để chọn bước học tiếp theo.

**Acceptance criteria:**

1. Backend lấy câu hỏi, đáp án và rubric đã duyệt từ LMS/database theo `assessment_id`; không tin rubric do trình duyệt gửi lên.
2. Kết quả dựa trên bằng chứng theo tiêu chí: khái niệm, lập luận, vận dụng và kiến thức nền.
3. Kết quả gồm trạng thái, bằng chứng, độ tin cậy, giới hạn và hành động tiếp theo.
4. Kết quả không được hiển thị như điểm chính thức và không tự ghi vào gradebook.
5. Ca độ tin cậy thấp hoặc mâu thuẫn tạo review case cho giảng viên.

### US-STU-13 — Phản tư cuối tuần

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn nhìn lại chênh lệch giữa kế hoạch và thực tế để cải thiện cách học tuần sau.

**Acceptance criteria:**

1. Hiển thị kế hoạch, thời gian thực tế, milestone, recovery và bằng chứng học tập liên quan.
2. AI tóm tắt nguyên nhân sai lệch nhưng không phán xét tính cách hoặc gắn nhãn năng lực cố định.
3. Sinh viên chọn một thay đổi cụ thể cho tuần sau.
4. Điều chỉnh chỉ cập nhật learner profile sau khi sinh viên xác nhận.
5. Working memory theo tuần được tách khỏi learner profile và mastery dài hạn.

### US-STU-14 — Trạng thái rỗng, đang xử lý và lỗi rõ ràng

**Ưu tiên:** P0
**User story:** Là sinh viên, tôi muốn biết hệ thống đang làm gì hoặc vì sao chưa thể trả lời để không hiểu nhầm dữ liệu demo là dữ liệu thật.

**Acceptance criteria:**

1. Workspace mới không hiển thị plan, session, quick check hay guidance mẫu.
2. Tác vụ AI có trạng thái đang xử lý và cho phép thử lại khi thất bại.
3. Empty state hướng dẫn hành động tiếp theo nhưng không tự tạo dữ liệu giả.
4. Timeout, lỗi LMS, lỗi model và lỗi quyền có thông báo khác nhau, không lộ stack trace.

## 5. User stories của giảng viên/cố vấn

### US-INS-01 — Đăng nhập và quản lý đúng lớp

**Ưu tiên:** P0
**User story:** Là giảng viên, tôi muốn chỉ truy cập các course mình phụ trách để dữ liệu lớp được phân quyền đúng.

**Acceptance criteria:**

1. Backend kiểm tra enrollment/role trên từng API.
2. Giảng viên không thể xem course không được phân công bằng cách sửa URL hoặc request.
3. Hành động quản lý được ghi audit log với actor, thời gian và đối tượng.

### US-INS-02 — Xem dashboard tiến độ tổng hợp

**Ưu tiên:** P0
**User story:** Là giảng viên, tôi muốn xem xu hướng deadline và điểm nghẽn kiến thức để hỗ trợ đúng nội dung.

**Acceptance criteria:**

1. Hiển thị tỷ lệ nộp đúng hạn, số ca rủi ro và xu hướng mastery theo chủ đề.
2. Chỉ hiển thị thống kê nhóm khi `n ≥ 5`.
3. Không hiển thị chat hoặc reflection thô của sinh viên.
4. Có trạng thái loading, empty, stale data và lỗi đồng bộ.

### US-INS-03 — Duyệt câu hỏi, đáp án và rubric

**Ưu tiên:** P0
**User story:** Là giảng viên, tôi muốn duyệt tiêu chí đánh giá trước khi AI sử dụng để kết quả bám đúng mục tiêu môn học.

**Acceptance criteria:**

1. Rubric có version, trạng thái nháp/đã duyệt và người duyệt.
2. Chỉ rubric đã duyệt mới được backend cấp cho Understanding Agent.
3. Thay đổi rubric không sửa ngược kết quả lịch sử; kết quả lưu rubric version đã dùng.
4. Mọi thay đổi có audit log.

### US-INS-04 — Xử lý hàng chờ review

**Ưu tiên:** P0
**User story:** Là giảng viên, tôi muốn xử lý các trường hợp AI không chắc chắn hoặc citation bị báo sai để hệ thống không tự kết luận quá mức.

**Acceptance criteria:**

1. Review case được lưu trong database, không chỉ nằm trong memory của agent.
2. Mỗi case có loại, bằng chứng, course, người tạo, độ ưu tiên và trạng thái.
3. Giảng viên có thể chấp nhận, sửa, từ chối hoặc yêu cầu thêm bằng chứng.
4. Quyết định được audit và có thể dùng làm dữ liệu evaluation đã khử định danh.

### US-INS-05 — Gửi hướng dẫn có kiểm soát

**Ưu tiên:** P1
**User story:** Là giảng viên, tôi muốn gửi hướng dẫn cho sinh viên cần hỗ trợ sau khi xem bằng chứng để tránh can thiệp sai đối tượng.

**Acceptance criteria:**

1. Hiển thị căn cứ và nội dung trước khi gửi.
2. Giảng viên phải xác nhận; AI không tự gửi.
3. Backend kiểm tra quyền, lưu trạng thái gửi và audit log.
4. Không gửi điểm, chẩn đoán tâm lý hoặc nhãn năng lực cố định.

## 6. User stories phi chức năng

| ID | Ưu tiên | Story | Acceptance criteria |
|---|---|---|---|
| US-NFR-01 | P0 | Là người dùng, tôi muốn dữ liệu được bảo vệ | HTTPS production; cookie `HttpOnly`, `Secure`, `SameSite`; secret không nằm trong Git; rate limit đăng nhập; session có thể thu hồi |
| US-NFR-02 | P0 | Là người dùng, tôi muốn hệ thống phản hồi ổn định | API thường có p95 theo SLO; AI có timeout và fallback; lỗi một course không làm mất toàn bộ workspace |
| US-NFR-03 | P0 | Là đội vận hành, tôi muốn quan sát được lỗi và chi phí | Có trace ID, latency, token/cost, retrieval metadata và error metrics; log không chứa secret/nội dung thô không cần thiết |
| US-NFR-04 | P0 | Là đội phát triển, tôi muốn tránh regression | CI chạy Ruff, backend tests, coverage toàn `src ≥ 80%`, deterministic eval, LMS tests, frontend unit/accessibility test và production build |
| US-NFR-05 | P0 | Là người dùng, tôi muốn giao diện có thể tiếp cận | Điều hướng bàn phím, label cho form, focus rõ, semantic HTML và không có vi phạm accessibility nghiêm trọng trong test |
| US-NFR-06 | P1 | Là đơn vị triển khai, tôi muốn hệ thống mở rộng an toàn | Worker tách khỏi API process; ingestion bất đồng bộ; vector store dùng service chung; dữ liệu được filter theo tenant/course/access scope |

## 7. Release slices

### Slice 1 — Vertical slice nền tảng

`US-STU-01`, `US-STU-02`, `US-STU-14`, `US-INS-01`, `US-NFR-01`, `US-NFR-04`.

**Đầu ra:** đăng nhập hai vai trò, dữ liệu LMS thật/mô phỏng đúng quyền, trạng thái lỗi/rỗng rõ ràng và CI pass.

### Slice 2 — Plan và theo dõi

`US-STU-03` đến `US-STU-08`.

**Đầu ra:** tạo, xác nhận, theo dõi và cảnh báo một kế hoạch tuần khả thi.

### Slice 3 — AI học tập và Recover

`US-STU-09` đến `US-STU-12`, `US-INS-03`, `US-INS-04`.

**Đầu ra:** Recover có HITL, RAG có citation, guardrail và đánh giá hiểu bài có rubric đáng tin cậy.

### Slice 4 — Reflect và quản lý lớp

`US-STU-13`, `US-INS-02`, `US-INS-05`, các NFR còn lại.

**Đầu ra:** khép kín vòng học tập và có dashboard/review workflow cho giảng viên.

## 8. Definition of Ready

Một story chỉ được đưa vào sprint khi:

- có persona, giá trị và acceptance criteria;
- có mock/API contract hoặc nguồn dữ liệu;
- xác định quyền truy cập và rủi ro HITL/privacy;
- có dependency, owner và reviewer;
- có cách kiểm thử happy path, error path và permission path.

## 9. Definition of Done

Một story được xem là hoàn thành khi:

- acceptance criteria đã được chứng minh bằng test hoặc UAT;
- backend không tin `user_id`, role, rubric hoặc quyền do client tự khai báo;
- có loading, empty, error, timeout và forbidden state phù hợp;
- unit/integration/frontend test liên quan pass;
- logging và audit không lộ secret;
- tài liệu/API schema được cập nhật cùng thay đổi;
- CI pass và có reviewer khác người viết.

## 10. Ngoài phạm vi

- AI làm hộ, nộp bài hoặc ghi điểm chính thức lên LMS.
- Tự động đổi lịch, gửi hướng dẫn hoặc kết luận năng lực khi chưa có người xác nhận.
- Xếp hạng sinh viên hoặc dùng dữ liệu phản tư để kỷ luật.
- Triển khai toàn trường và load test 1.000 người dùng trong MVP hiện tại.
