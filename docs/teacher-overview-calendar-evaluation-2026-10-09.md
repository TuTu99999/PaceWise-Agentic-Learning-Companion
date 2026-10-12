# Tổng quan giảng viên và Google Calendar — kiểm chứng 09/10/2026

## Kết quả và phạm vi

Đã sửa Tổng quan cho đúng scope Plan–Do–Reflect: quan sát tiến độ tổng hợp, deadline sắp đến, nguồn học liệu cho Do và đường vào HITL. Không thêm hệ thống phản hồi/chấm điểm thay Canvas. Đã rebuild backend, worker, frontend và LMS simulator local, không xóa database hay volume.

Google: kết thúc transaction xác thực/đọc trước khi chờ provider; lưu từng event link sau khi tạo thành công; retry bỏ qua link đã lưu; cache token/account/freebusy mã hóa bằng Fernet. Đây là kiểm chứng kỹ thuật, không phải chứng minh phục vụ 1.000 tài khoản Google đồng thời.

## Những điểm đã sửa

- Bỏ nút/modal gửi khuyến nghị ôn tập trùng chức năng phản hồi LMS, bỏ khối thống kê quản trị LMS và select nhóm chỉ có một lựa chọn. Vẫn giữ KPI, cảnh báo deadline, trạng thái index học liệu và Hàng chờ duyệt.
- Bỏ `missingMinutes` suy từ điểm bài tập. Dashboard không còn nói “giờ chưa được bảo vệ” khi chưa đối chiếu lịch, workload và capacity thực tế.
- “Nguy cơ” được diễn đạt đúng là tín hiệu bài chưa nộp, deadline trong 72 giờ; không phải xác suất trễ hoặc bằng chứng sinh viên chưa hiểu.
- KPI chỉ tính bài đã công bố, đến hạn theo từng sinh viên, loại miễn bài và đếm task–student duy nhất. Ưu tiên thời điểm nộp đầu tiên; không mặc định timestamp/late thiếu là đạt hay trượt. Trường hợp đã nộp nhưng thiếu dữ liệu thời điểm được ghi unknown và loại khỏi tỷ lệ.
- Chưa có bài đến hạn: hiển thị “Chưa có dữ liệu”, không tạo một tuần giả có tỷ lệ 0%.
- Tổng hợp chủ đề dùng bằng chứng điểm hợp lệ mới nhất theo sinh viên/KC, không giữ lỗi cũ khi đã có bằng chứng mới tốt hơn. Mẫu số là số sinh viên được quan sát cho chủ đề; chỉ hiện khi mẫu này đạt ngưỡng tối thiểu 5. Điểm LMS không được gọi là assessment hiểu bài của Do.
- Không tự đưa tất cả điểm LMS dưới 70% vào HITL: điểm thấp không đồng nghĩa AI thiếu confidence. Hàng chờ lấy các ca Assessment/citation đã được đưa vào queue thực sự.
- Cache được version lại để không dùng projection cũ; đổi môn, stale cache, live revision và response đến trễ được xử lý đúng. Lỗi tải lại được hiển thị cùng nút retry. Bị thu hồi quyền/401–403: xóa cache và dữ liệu giảng viên trong UI, không tiếp tục hiển thị bản cũ.
- Ngày/tuần, deadline hiển thị theo Asia/Ho_Chi_Minh. Không lấy tuần theo timezone máy chủ.
- Tổng quan giảm từ 11 xuống 7 API LMS; dùng một HTTP pool giới hạn 8 kết nối cho một lượt snapshot. Đợi sibling requests kết thúc trước khi đóng pool khi upstream lỗi; không dùng client chứa cookies chung giữa các tài khoản.

## Regression — output thực tế

| Case | Output kiểm tra | Kết quả |
|---|---|---|
| Draft, miễn bài, gia hạn riêng, duplicate assignment, nộp lại sau deadline | `count=2, total=2, unknown=1, rate=1.0`; lần nộp đầu được tính; bài miễn/gia hạn chưa đến hạn không tính | Pass |
| Deadline gần nửa đêm UTC | `2026-10-04T18:30Z` thuộc tuần `05/10` tại Việt Nam | Pass |
| Chủ đề: 5 sinh viên được quan sát, 1 điểm thấp | `needsSupport=1, n=5`; có bằng chứng mới tốt hơn → danh sách tín hiệu rỗng | Pass |
| Chủ đề chỉ có 1 người, score thiếu/NaN hoặc user không thuộc lớp | Không phát sinh aggregate chủ đề | Pass |
| Deadline riêng được gia hạn, bài draft, miễn bài | Chỉ 1 sinh viên cần chú ý; không trả `missingMinutes` | Pass |
| Chưa có bài đến hạn | `onTimeTotal=0`, `weeklyCompletion=[]`, `progressImprovement=null`; UI không hiện 0% | Pass |
| Đổi môn khi response cũ hoặc refresh đang chạy | Response môn cũ không dispatch vào môn mới | Pass |
| Cache bị stale dù LMS revision không đổi | Có request revalidation; không mắc kẹt ở snapshot cũ | Pass |
| Lỗi refresh / thu hồi enrollment | Lỗi thường giữ bản gần nhất và cảnh báo; 403 xóa cache/aggregate/review data | Pass |
| Pool database chỉ 1 connection, Google đang chờ | Status, freebusy, export, callback, disconnect: `checkedout=0` tại upstream await; request `/auth/me` song song vẫn 200; xong request pool trả hết | **5/5 pass** |
| Google access token cache | Hai đọc cùng grant → 1 outbound; đổi grant → outbound thứ 2; ciphertext DB không chứa `SENSITIVE_TOKEN`; provider I/O không giữ cache connection | Pass |
| Export gặp 429 giữa chừng | Lần đầu tạo 1 event rồi 429 + `Retry-After:20`, `Partial-Created:1`; retry bỏ qua block `one`, chỉ tạo block `two`; tổng create calls=3 | Pass |
| HTTP pool LMS khi 1 request lỗi | Chỉ tạo 1 HTTP client; sibling hoàn tất trước khi đóng pool; lỗi upstream vẫn được trả | Pass |

Full backend: **560 passed**, [JUnit](../evals/reports/teacher-calendar-backend-2026-10-09.xml). Full frontend: **217 passed / 54 files**, [JUnit](../evals/reports/teacher-calendar-frontend-2026-10-09.xml). Docker production build/typecheck pass. Lint các module/test mới và `git diff --check` pass.

Bộ Google chạy lại sau bổ sung assertion cache không giữ connection: **38 passed**, [JUnit](../evals/reports/google-pool-cache-export-2026-10-09.xml).

## Local Docker/PostgreSQL

Kiểm tra HTTP encrypted, không in hồ sơ/keys/ticket/cookie:

- Giảng viên: `/instructor/overview` **200**, lớp **28 sinh viên**, kiểm tra ngưỡng mẫu chủ đề pass; không có suy luận thời lượng từ điểm hay grade-as-uncertain-AI review.
- Sinh viên gọi endpoint giảng viên: **403**.
- Độ trễ một lượt đo trước/sau gộp HTTP client: **1797 ms → 846 ms**. Đây là smoke local, không phải benchmark p95/p99 hoặc SLA; điều kiện tải/cache giữa hai lượt không được kiểm soát như thí nghiệm hiệu năng.
- Hai role: login **200** → sang LMS JSON/CORS **200** → quay PaceWise **200** → logout **200**. Replay ticket, cookie cũ và phiên LMS liên kết sau logout đều **401**. Không đưa danh tính/ticket vào URL.

Script chạy lại: `scripts/evaluate_instructor_overview.py`, `scripts/evaluate_auth_bridge.py`. Các script dùng tài khoản demo và thu hồi phiên test trong luồng kiểm tra. Không tạo lịch Google thật hoặc chạy load bằng credential người dùng.

## Giới hạn còn lại

- Pool regression dùng SQLite QueuePool nhỏ để tái hiện retention; runtime smoke chạy trên PostgreSQL nhưng chưa phải load test PostgreSQL/Google 1.000 user.
- Cảnh báo 72 giờ chưa dự đoán cá nhân hóa mức thiếu thời gian; không tính sinh viên chắc chắn trễ hay biết mức hiểu từ điểm LMS.
- Aggregate chủ đề dựa trên snapshot evidence LMS tối đa 500 bản ghi được lấy về. Không có tín hiệu không đồng nghĩa cả lớp đã hiểu; dashboard chỉ nói chưa có tín hiệu đủ dữ liệu.
- HITL vẫn có bằng chứng trích đoạn cần xem trong queue theo phân quyền; tổng quan không hiển thị các trích đoạn đó. Ngưỡng nhóm ≥5 giảm nguy cơ nhận diện, không phải chứng nhận tuân thủ FERPA hay bảo đảm không thể tái nhận diện.
- Test HTTP/DOM không thay cho kiểm tra UI trình duyệt thật ở mọi kích thước; chưa chạy pilot hoặc kiểm toán bảo mật độc lập.

Sau update: Ctrl+F5 tại `http://localhost:5173` để lấy bundle/cache version mới.
