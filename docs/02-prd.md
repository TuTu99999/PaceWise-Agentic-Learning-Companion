# PRD — PaceWise

**Phiên bản:** 1.0 · **Đội:** P-008 · **Cập nhật:** 24/09/2026
**Trạng thái:** scope P0 đã khóa; các mục P1 phụ thuộc sandbox/credential và release gate.

## 1. Bối cảnh và mục tiêu

Canvas quản lý course, assignment, deadline và submission, nhưng chưa giúp sinh viên chuyển dữ liệu của nhiều môn thành một kế hoạch tuần phù hợp với quỹ thời gian và mức độ hiểu bài. Khi thời gian thực tế lệch khỏi dự kiến hoặc sinh viên chưa nắm kiến thức nền, rủi ro thường chỉ lộ rõ gần deadline.

PaceWise là learning companion theo chu trình **Plan–Do–Reflect**:

- **Plan:** lập kế hoạch tuần từ nhiệm vụ, deadline và quỹ thời gian.
- **Do:** theo dõi thực tế, hỏi đáp có nguồn, kiểm tra nhanh mức hiểu bài và phục hồi kế hoạch khi cần.
- **Reflect:** tìm nguyên nhân sai lệch và hiệu chỉnh ước lượng cho tuần sau.

### Mục tiêu P0

1. Giúp sinh viên biết việc tiếp theo và lý do ưu tiên.
2. Phát hiện sớm khi kế hoạch không còn khả thi.
3. Đề xuất phương án phục hồi nhưng không tự ý đổi lịch.
4. Biến bằng chứng học tập thành hành động tiếp theo.
5. Cho giảng viên thấy xu hướng tổng hợp và ca cần duyệt mà không biến hệ thống thành công cụ giám sát cá nhân.

### Nguyên tắc

- AI hỗ trợ ra quyết định; con người chịu trách nhiệm cho hành động có tác động.
- Không làm hộ bài tính điểm.
- Trả lời từ tài liệu môn học có trích dẫn; thiếu nguồn thì nói rõ.
- Đánh giá hiểu bài chỉ mang tính hỗ trợ, không phải điểm số.
- P0 phải chạy được không phụ thuộc Canvas thật.

## 2. Người dùng và quyền hạn

| Vai trò | Mô tả | Mục tiêu | Quyền |
|---|---|---|---|
| Sinh viên | Học một môn pilot, có nhiều nhiệm vụ và quỹ thời gian hữu hạn | Duy trì kế hoạch khả thi, nộp đúng hạn, biết phần cần ôn | Xem dữ liệu cá nhân; tạo/xác nhận kế hoạch; cập nhật tiến độ; hỏi đáp; làm kiểm tra nhanh; phản tư |
| Giảng viên/cố vấn | Theo dõi lớp và duyệt nội dung đánh giá | Phát hiện sớm điểm nghẽn, hỗ trợ đúng chỗ | Duyệt mục tiêu/câu hỏi/rubric; xem tổng hợp nhóm; xử lý hàng chờ; xác nhận hỗ trợ |
| Hệ thống | Điều phối workflow và thực thi quy tắc | Đưa ra gợi ý có thể kiểm tra | Không tự gửi tin, đổi lịch, ghi điểm hay chia sẻ dữ liệu |

P0 có hai bề mặt:

- **Student Experience:** web độc lập; P1 có thể mở từ Canvas qua LTI 1.3.
- **Management Console:** web cho giảng viên/cố vấn, dùng chung backend và RBAC.

## 3. Phạm vi

### 3.1 P0 bắt buộc

- Một môn pilot và 3–5 đơn vị kiến thức.
- Canvas fixture có schema tương thích adapter REST.
- Đăng nhập mô phỏng, phân quyền hai vai trò.
- Kế hoạch tuần có milestone, thời lượng, thứ tự, deadline và giải thích ưu tiên.
- Lịch PaceWise độc lập, Google Calendar OAuth tùy chọn và xuất `.ics` không cần tài khoản ngoài.
- Cập nhật thời gian thực tế và trạng thái công việc.
- Phát hiện nguy cơ theo quy tắc xác định trước; AI chỉ giải thích.
- Tạo 2–3 phương án phục hồi và yêu cầu sinh viên xác nhận.
- RAG trên tài liệu môn học, trích dẫn tới đoạn nguồn.
- Guardrail nhiều lớp với yêu cầu làm hộ bài.
- Kiểm tra nhanh 1–3 câu và trạng thái bằng chứng học tập.
- Phiên Reflect cuối tuần.
- Dashboard lớp tổng hợp, ngưỡng ẩn danh và hàng chờ giảng viên.
- Logging, tracing, metrics, ba bộ đánh giá ≥120 mẫu và deploy online.

### 3.2 P1 sau release gate

- Canvas REST chỉ đọc với sandbox/token.
- LTI 1.3 với developer key.
- Memory dài hạn qua nhiều tuần.
- Reranker/model dịch vụ và định tuyến model nâng cao.
- Load test 1.000 người dùng đồng thời.

### 3.3 Không làm

- Làm hộ, nộp bài, chấm điểm chính thức hoặc ghi điểm lên Canvas.
- Fork/chỉnh sửa mã nguồn Canvas LMS.
- Triển khai toàn trường hoặc hỗ trợ tất cả môn.
- Tự động gửi email, thay deadline, đổi lịch cá nhân hoặc can thiệp sinh viên.
- Xếp hạng hay gắn nhãn năng lực cố định.

## 4. User stories và tiêu chí chấp nhận

| ID | Ưu tiên | User story | Tiêu chí chấp nhận |
|---|---|---|---|
| US-01 | P0 | Là sinh viên, tôi muốn thấy nhiệm vụ từ Canvas để không nhập lại | Fixture luôn chạy; adapter thật có timestamp đồng bộ và trạng thái lỗi |
| US-02 | P0 | Tôi muốn khai báo quỹ thời gian để kế hoạch không vượt khả năng | Tổng thời lượng không vượt slot; xung đột được báo rõ |
| US-03 | P0 | Tôi muốn AI chia assignment thành milestone | Mỗi milestone có đầu ra, thời lượng, deadline nội bộ và nguồn assignment |
| US-04 | P0 | Tôi muốn xem trước kế hoạch trước khi lưu | Chỉ ghi DB sau khi bấm xác nhận; thay đổi được audit |
| US-05 | P0 | Tôi muốn cập nhật thời gian thực tế | Hệ thống tính lại sai lệch và nguy cơ trong ≤2 giây, không cần gọi LLM |
| US-06 | P0 | Tôi muốn phương án phục hồi khi có nguy cơ trễ | Có 2–3 phương án, nêu đánh đổi và bảo vệ deadline quan trọng khi còn nghiệm |
| US-07 | P0 | Tôi muốn hỏi tài liệu môn học | Câu trả lời có trích dẫn hoặc từ chối khi không đủ nguồn |
| US-08 | P0 | Tôi muốn được gợi ý chứ không nhận bài làm sẵn | Yêu cầu làm hộ bị chặn/chuyển thành gợi ý từng bước |
| US-09 | P0 | Tôi muốn biết phần vừa học đã hiểu tới đâu | Kết quả có bằng chứng, độ tin cậy, giới hạn và bước tiếp theo |
| US-10 | P0 | Tôi muốn nhìn lại tuần học | Reflect so sánh dự kiến–thực tế và lưu một điều chỉnh cụ thể |
| US-11 | P0 | Là giảng viên, tôi muốn thấy xu hướng lớp | Chỉ hiện nhóm n≥5, không lộ chat/phản tư thô |
| US-12 | P0 | Tôi muốn duyệt câu hỏi và ca không chắc chắn | Có hàng chờ, thông tin giải thích và audit quyết định |
| US-13 | P0 | Tôi muốn dùng lịch bận thực tế khi lập kế hoạch | Có thể đọc busy/free từ Google; không đọc tiêu đề/nội dung sự kiện; email Google có thể khác email trường |
| US-14 | P0 | Tôi không muốn cấp quyền Google nhưng vẫn muốn dùng lịch ngoài | Tải được `.ics` từ kế hoạch đã lưu và import vào ứng dụng lịch hỗ trợ chuẩn này |

## 5. Luồng nghiệp vụ chi tiết

### 5.1 Khởi tạo và nạp dữ liệu

1. Người dùng đăng nhập và hệ thống xác định vai trò.
2. Sinh viên chọn môn pilot.
3. Adapter đọc Canvas fixture. Nếu có credential, người dùng có quyền mới được bật Canvas REST read-only.
4. Hệ thống chuẩn hóa course, assignment, deadline, submission status và tài liệu.
5. Màn hình hiển thị thời điểm đồng bộ, nguồn dữ liệu và các trường thiếu.
6. Nếu chưa có dữ liệu, hiển thị empty state kèm lựa chọn tải fixture; không gọi AI.

**Lỗi:** khi Canvas không truy cập được, dùng bản đồng bộ gần nhất, gắn nhãn “dữ liệu cũ” và cho phép thử lại. Không suy đoán deadline bị thiếu.

### 5.2 Plan — lập kế hoạch tuần

Tab Kế hoạch là nơi tạo, xem trước, xác nhận và theo dõi plan đã lưu. Màn hình hiển thị timeline hợp nhất trong cửa sổ 7 ngày: lịch học, quiz, kỳ thi và deadline từ LMS là các mốc **chỉ đọc**; study block do PaceWise tạo có thể đưa vào Recover; khoảng không thể học là hard constraint. Sinh viên có thể lọc `Tất cả`, `Lịch LMS`, `Kế hoạch học` hoặc `Lịch bận`; việc hiển thị chung không làm thay đổi quyền sở hữu dữ liệu của từng nguồn.

1. Sinh viên chọn tuần, mục tiêu, quỹ thời gian từng ngày và khung giờ không thể dùng.
2. Bộ lập lịch xác định trước kiểm tra deadline, thời lượng và phụ thuộc.
3. LLM đề xuất cách chia assignment thành milestone có đầu ra kiểm chứng được.
4. Bộ kiểm tra schema và lịch loại phương án vượt quỹ thời gian, đặt sau deadline hoặc thiếu phụ thuộc.
5. Hệ thống xếp ưu tiên theo deadline, trọng số assignment group do giảng viên cấu hình trong LMS, mức ưu tiên cá nhân, tiến độ và mức rủi ro.
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

#### Chính sách nhắc việc

- Nhắc study block trước 15 phút; buổi học online trước 10 phút; quiz trước 30 phút.
- Ở mốc 72 giờ trước deadline, chỉ nhắc khi sinh viên chưa bắt đầu hoặc tổng study block còn lại không đủ thời lượng ước tính.
- Ở mốc 24 giờ, nhắc nếu nhiệm vụ chưa hoàn thành; ở mốc 2 giờ, cảnh báo khẩn nếu LMS chưa ghi nhận bài nộp.
- Thi giữa kỳ/cuối kỳ được nhắc trước 24 giờ và 60 phút. Study block bị lỡ hoặc lịch LMS thay đổi gây xung đột sẽ cảnh báo ngay và dẫn tới Recover.
- Giới hạn tối đa ba thông báo trình duyệt chủ động mỗi ngày. Nhắc thông thường còn lại được giữ trong trung tâm thông báo và gộp thành tóm tắt lúc 20:00; cảnh báo vẫn luôn hiển thị trong ứng dụng.
- Quyền thông báo trình duyệt chỉ được xin sau thao tác chủ động của người dùng; trạng thái đã gửi/đã đọc được lưu để không gửi trùng sau khi tải lại hoặc đổi thiết bị.

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
- sinh viên chủ động yêu cầu;
- sinh viên thêm, kéo dài, rút ngắn hoặc xóa một khoảng không thể học;
- lịch LMS mới tạo xung đột với study block đã xác nhận.

Luồng:

1. Hệ thống chụp snapshot kế hoạch hiện tại.
2. Bộ lập lịch tạo các phương án hợp lệ; LLM diễn giải đánh đổi.
3. Mỗi phương án nêu việc giữ, việc dời, thời gian thiếu/dư, deadline được bảo vệ và rủi ro còn lại.
4. Nếu không còn nghiệm khả thi, hệ thống nói rõ và gợi ý trao đổi với giảng viên.
5. Sinh viên chọn, sửa hoặc bỏ qua.
6. Màn hình xác nhận hiển thị diff trước–sau.
7. Chỉ sau xác nhận, lịch mới được cập nhật; snapshot cũ vẫn nằm trong audit log.

#### Thay đổi quỹ thời gian của sinh viên

1. Sinh viên chỉ nhập khoảng thời gian không thể học; không cần khai báo hoặc chứng minh lý do.
2. Khoảng bận mới/kéo dài trở thành hard constraint. Study block bị trùng không bị sửa âm thầm mà tạo `schedule_conflict`.
3. Khoảng bận bị xóa/rút ngắn tạo `capacity_released`; hệ thống không tự nhồi thêm việc vào thời gian mới trống.
4. Deadline, điểm, trạng thái nộp và lịch thi từ LMS không thay đổi vì thao tác này.
5. Nếu còn nghiệm, hệ thống tạo bản diff đa môn để sinh viên xác nhận. Nếu vô nghiệm, hệ thống nêu số phút thiếu và khuyến nghị chủ động trao đổi với giảng viên.
6. PaceWise không xác minh sinh viên nói thật hay nói dối vì thay đổi lịch cá nhân không tạo ngoại lệ học vụ.

#### Thay đổi động từ LMS

Lịch học, quiz, kỳ thi và deadline là **constraint có phiên bản**, không phải dữ liệu được sao chép một lần:

1. LMS event chỉ đóng vai trò kích hoạt; PaceWise đọc lại trạng thái mới nhất qua REST.
2. Snapshot mới được so với snapshot gần nhất theo `course`, `assignment` và `calendar event`.
3. Nếu sự kiện được thêm/kéo dài và trùng study block, hệ thống tạo `schedule_conflict` và mở Recover.
4. Nếu sự kiện bị xóa/rút ngắn, hệ thống tạo `capacity_released`; khoảng trống chỉ được đề xuất, không tự nhồi thêm việc.
5. Nếu deadline dời sớm, toàn bộ task đa môn được xếp lại theo deadline và capacity; nếu dời muộn, hệ thống báo phần dự phòng vừa được giải phóng.
6. Nếu assignment bị xóa, các block liên quan chỉ được gỡ sau khi sinh viên xác nhận.
7. Thay đổi không ảnh hưởng plan được cập nhật im lặng; thay đổi có ảnh hưởng hiển thị impact summary, còn phương án Recover luôn có diff trước–sau.

`Look-ahead horizon` là 14 ngày để phát hiện xung đột sớm. Sinh viên chọn `planning week` là tuần hiện tại hoặc tuần tiếp theo, mỗi tuần cố định từ Thứ Hai đến Chủ Nhật. Khi lập tuần hiện tại, hệ thống không xếp block vào ngày đã qua; task hạn ở tuần sau chỉ nhận một milestone tỷ lệ phù hợp, không bị ép hoàn thành toàn bộ ngay trong tuần hiện tại.

### 5.7 Reflect — cuối tuần

1. Reflect dùng **tuần học cố định từ Thứ Hai 00:00 đến Chủ Nhật 23:59**, không dùng cửa sổ cuốn bảy ngày. Look-ahead deadline 14 ngày và planning window là các khái niệm riêng.
2. Mặc định Weekly Reflect mở lúc **20:00 Chủ Nhật theo `Asia/Ho_Chi_Minh`**. Nếu còn study block vào tối Chủ Nhật, cửa sổ mở sau block cuối; nếu sinh viên bỏ qua, họ có thể hoàn thành bù đến 09:00 sáng Thứ Hai.
3. Hệ thống chỉ tổng hợp kế hoạch, thời gian thực tế, milestone, task hoàn thành và block bị lệch nằm trong đúng tuần được phản tư.
4. Sinh viên trả lời ba câu: việc nào hoàn thành/chưa hoàn thành; nguyên nhân khiến kế hoạch đúng hoặc lệch; tuần sau cần đổi thời lượng, khung giờ hay cách chia task nào.
5. AI tóm tắt nhưng không phán xét tính cách/năng lực.
6. Sinh viên chọn một điều chỉnh: hệ số ước lượng, khung giờ, cách chia việc hoặc đơn vị kiến thức cần ôn.
7. Điều chỉnh được gắn với `effective_week_start` của Thứ Hai kế tiếp và làm đầu vào cho bản nháp kế hoạch tuần sau. Hệ thống không tự áp dụng kế hoạch nếu sinh viên chưa xác nhận.
8. Ghi chú ngắn sau phiên học là `session note`, không thay thế Weekly Reflect.

### 5.8 Giảng viên/cố vấn

1. Dashboard hiển thị tỷ lệ đúng hạn, số ca nguy cơ, trạng thái bằng chứng theo đơn vị kiến thức và xu hướng theo tuần.
2. Chỉ nhóm n≥5 được hiển thị; không có nội dung chat/phản tư thô.
3. Giảng viên duyệt mục tiêu, câu hỏi, đáp án và rubric trước khi dùng.
4. Hàng chờ gồm ca độ tin cậy thấp, nguồn bị báo sai và tín hiệu cần hỗ trợ.
5. Trước khi gửi một hỗ trợ hướng tới cá nhân, giảng viên xem lý do, dữ liệu được dùng và xác nhận.

## 6. Human-in-the-loop

| Hành động | Rủi ro | Người xác nhận | Thông tin phải thấy |
|---|---|---|---|
| Lưu kế hoạch tuần | Ghi sai lịch cá nhân | Sinh viên | Toàn bộ slot, xung đột, deadline, giả định |
| Tạo sự kiện Google | Ghi dữ liệu ra dịch vụ ngoài | Sinh viên | Tài khoản đang kết nối, số study block, thời gian và nút hủy |
| Phục hồi kế hoạch | Dời việc quan trọng | Sinh viên | Diff trước–sau, đánh đổi, rủi ro còn lại |
| Duyệt câu hỏi/rubric | Đánh giá sai mục tiêu | Giảng viên/SME | Mục tiêu, câu, đáp án, rubric, nguồn |
| Kết luận ca không chắc chắn | Gắn nhãn sai | Giảng viên | Bằng chứng, độ tin cậy, lý do từ chối kết luận |
| Hỗ trợ cá nhân | Ảnh hưởng riêng tư | Giảng viên | Đối tượng, nội dung, căn cứ, kênh gửi |
| Xóa dữ liệu | Không thể khôi phục ngay | Chủ dữ liệu/admin | Phạm vi, thời hạn xử lý, chính sách backup |

## 7. Lỗi và giới hạn

| Tình huống | Phản hồi cho người dùng | Xử lý hệ thống |
|---|---|---|
| Canvas lỗi/quá hạn token | “Không đồng bộ được; đang dùng dữ liệu lúc…” | Dùng snapshot; retry có backoff |
| Không đủ tài liệu | “Chưa đủ nguồn để kết luận” | Không gọi model lớn; log ca thiếu nguồn |
| LLM sai schema | Hiển thị thử lại, không lưu kết quả | Validate; retry tối đa 1 lần; fallback |
| Provider hết quota | Thông báo tạm thời và cho dùng chức năng không-AI | Circuit breaker; chuyển provider nếu đã cấu hình |
| Timeout >30 giây | Dừng tác vụ và cho thử lại | Hủy job; lưu trace lỗi |
| Kế hoạch vô nghiệm | Nêu số giờ thiếu và deadline xung đột | Không sinh lịch giả |
| Độ tin cậy thấp | Không kết luận | Chuyển hàng chờ giảng viên |
| Yêu cầu làm hộ | Giải thích ranh giới và đưa gợi ý học | Log loại guardrail, không lưu nội dung nhạy cảm thừa |
| Google OAuth bị từ chối/hết hạn | Giữ nguyên lịch PaceWise; cho kết nối lại hoặc tải `.ics` | Không mất kế hoạch; không dùng token lỗi; không tự retry ghi sự kiện |

Giới hạn phải hiển thị rõ: dữ liệu Canvas có thể cũ; ước lượng không bảo đảm kết quả; bằng chứng học tập không phải điểm; cảnh báo không thay thế trao đổi với giảng viên.

## 8. Dữ liệu và quyền riêng tư

### Nguồn dữ liệu

- Canvas fixture: course, assignment, deadline, submission status, syllabus.
- Canvas REST read-only khi có credential.
- Tài liệu môn do đội/giảng viên được phép dùng.
- Dữ liệu người dùng nhập: quỹ thời gian, tiến độ, câu trả lời kiểm tra, lựa chọn phục hồi.
- Google Calendar: chỉ busy/free, email tài khoản để hiển thị kết nối và ID sự kiện do PaceWise tạo; `.ics` được sinh theo yêu cầu và không lưu trên server.
- Dữ liệu đánh giá công khai, mô phỏng hoặc đã thay định danh.

### Chính sách

- RBAC tách sinh viên và giảng viên.
- Mã định danh pilot được thay bằng mã giả.
- Dashboard chỉ tổng hợp nhóm n≥5.
- Không đưa chat/phản tư thô vào dashboard hoặc analytics.
- Log vận hành giữ 30 ngày.
- Dữ liệu pilot đã thay định danh giữ 90 ngày.
- Yêu cầu xóa hoàn tất trong 30 ngày; backup hết hạn trong 30 ngày tiếp theo.
- Secret chỉ nằm trong secret manager/.env cục bộ, không commit.
- Không dùng dữ liệu để xếp hạng, kỷ luật hay chấm điểm chính thức.

## 9. Đánh giá và metrics

### 9.1 Ba bộ đánh giá

Mỗi bộ có ít nhất 120 mẫu, version hóa, tách development/test và không dùng test để sửa prompt:

1. **planning_v1:** bình thường, quá tải, xung đột, nguy cơ và phục hồi.
2. **grounding_safety_v1:** trả lời được/không trả lời được, injection, câu hỏi hợp lệ, yêu cầu làm hộ.
3. **understanding_journey_v1:** câu hỏi/rubric, câu trả lời có nhầm lẫn và hành trình Plan–Do–Reflect.

Với dữ liệu hiểu bài: SME duyệt; hai người gán nhãn độc lập; người thứ ba phân xử; báo cáo Cohen’s kappa hoặc Krippendorff’s alpha.

### 9.2 Ngưỡng AI/reliability

| Nhóm | Metric | Ngưỡng P0 |
|---|---|---:|
| Plan | Kế hoạch đúng ràng buộc | ≥95% |
| Recover | Bảo vệ deadline quan trọng khi còn nghiệm | ≥90% |
| Risk | Recall / precision | ≥85% / ≥75% |
| Grounding | Trích dẫn hợp lệ | ≥95% |
| Grounding | Từ chối đúng khi thiếu nguồn | ≥90% |
| Integrity | Tỷ lệ sinh đáp án làm hộ | ≤5% |
| Integrity | Chặn nhầm yêu cầu hợp lệ | ≤10% |
| Check | Câu hỏi/đáp án không lỗi | ≥95% |
| Check | Bám mục tiêu kiến thức | ≥90% |
| Diagnosis | Macro-F1 so với nhãn chuẩn | ≥0,80 |
| Diagnosis | Lỗi ở ca độ tin cậy cao | ≤5% |

RAGAS đo faithfulness và answer relevance; metric xác định trước kiểm tra citation, schema, deadline và guardrail; LLM-as-Judge chỉ dùng sau khi hiệu chuẩn với nhãn người.

### 9.3 KPI sản phẩm

Đây là mục tiêu pilot:

- Tỷ lệ nộp đúng hạn tăng ≥10 điểm phần trăm so với baseline cùng môn/nhóm.
- ≥70% ca nguy cơ còn khả thi có phương án phục hồi được xác nhận trước deadline.
- Trung vị sai số thời gian dự kiến–thực tế giảm ≥20% sau ba tuần.
- ≥60% bằng chứng học tập dẫn tới hành động tiếp theo.

Baseline, cohort, kỳ quan sát và công thức phải được lưu cùng báo cáo; không suy diễn quan hệ nhân quả nếu không có thiết kế thử nghiệm phù hợp.

Dashboard Progress lưu tối đa một snapshot mỗi ngày cho các chỉ số vận hành pilot:

| Metric | Công thức | Ý nghĩa |
|---|---|---|
| Plan coverage | deadline đang mở có ≥1 study block / tổng deadline đang mở | Sinh viên đã biến deadline thành hành động hay chưa |
| At-risk deadline | số task có `capacity_gap` hoặc `missed_progress` | Rủi ro được phát hiện trước hạn |
| On-time submission | submission không late / submission đã chấm | KPI kết quả chính |
| Estimate MAE | trung bình `abs(actual-estimate)/estimate` | Khả năng ước lượng được cải thiện hay không |
| Recovery count | số phương án được sinh viên xác nhận | Mức sử dụng Recover |

Các snapshot trên là telemetry sản phẩm, không thay thế thiết kế pilot ≥100 mẫu và không tự chứng minh quan hệ nhân quả.

### 9.4 Hiệu năng và chi phí

- Hỏi đáp p95 ≤8 giây.
- Plan/Recover p95 ≤15 giây.
- Hard timeout 30 giây.
- Báo cáo p50/p95/error rate/token/cost/cache hit/model route.
- Load test P0: 100 virtual users với kịch bản pha trộn.
- 1.000 người đồng thời là P1/stretch, không tuyên bố nếu chưa có bằng chứng.

## 10. Tech stack và vận hành

| Lớp | Lựa chọn |
|---|---|
| Frontend | Next.js, React, TypeScript |
| Backend | FastAPI, Pydantic |
| Agent | LangGraph |
| Model gateway | OpenRouter; model nhỏ mặc định, model lớn cho Reflect khó |
| RAG | Qdrant, embedding đa ngôn ngữ, bge-reranker; Cohere Rerank tùy cấu hình |
| Guardrail | Quy tắc nhanh + semantic classifier hiệu chuẩn + policy kiểm tra output |
| Data | PostgreSQL |
| Calendar | Google OAuth 2.0/Calendar REST tùy chọn; RFC 5545 `.ics` fallback |
| Cache/rate limit | Redis |
| Eval | Pytest + RAGAS + deterministic metrics + LLM-as-Judge hiệu chuẩn |
| Observability | OpenTelemetry, Prometheus, Grafana hoặc dịch vụ tương đương |
| Deploy | Docker; Render hoặc GCP Cloud Run sau khi chốt ngân sách |

Mỗi request có request_id, user role, workflow, model, prompt version, latency, token, cost estimate, cache status và error class. Không log secret hoặc nội dung học tập thô nếu không cần cho mục đích đã công bố.

## 11. Quyết định còn mở

| Mục | Chủ sở hữu | Hạn | Fallback |
|---|---|---|---|
| Môn pilot và 3–5 đơn vị kiến thức | PO + BA | Cuối tuần 1 | Bộ môn mô phỏng đã duyệt |
| SME duyệt nội dung | BA | Cuối tuần 1 | Hoãn đánh giá mở, chỉ demo câu đóng |
| Canvas sandbox/token | Tech Lead | Cuối tuần 1 | Fixture |
| LTI developer key | Tech Lead | Cuối tuần 1 | Web độc lập |
| Model/prompt version | AI Engineer | Đầu tuần 3 | Model nhỏ mặc định |
| Hosting/ngân sách | Tech Lead + PO | Cuối tuần 2 | Gói staging chi phí thấp |
| Ngoại lệ tech stack | Tech Lead + mentor | Cuối tuần 1 | Dùng stack trong PRD |

## 12. Release gate P0

Chỉ gọi là MVP có thể pilot khi:

- Hai vai trò đăng nhập đúng quyền.
- Happy path Plan–Do–Reflect chạy end-to-end bằng fixture.
- Recover có diff và xác nhận.
- Hỏi đáp có nguồn và guardrail vượt ngưỡng.
- Kiểm tra hiểu bài có rubric, độ tin cậy và đường chuyển giảng viên.
- Ba bộ đánh giá đều ≥120 mẫu và đạt ngưỡng hoặc có báo cáo ngoại lệ.
- Dashboard tuân thủ n≥5 và không lộ dữ liệu thô.
- p95/error rate/load test đạt mục tiêu P0.
- Có dashboard/log/trace, runbook rollback và deploy online.
- QA chính tả, thuật ngữ, link, Mermaid và thông tin đội đã hoàn tất.
