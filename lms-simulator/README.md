# Canvas LMS lightweight simulator

Bản Canvas gọn nhẹ dùng để phát triển và kiểm thử tích hợp PaceWise mà không
cần khởi động toàn bộ Canvas Rails. Simulator giữ các khái niệm chính của
Canvas: course, enrollment, assignment, submission, module, tài liệu, grade,
quiz, rubric, outcome, calendar và inbox.

## Chạy local

```powershell
cd "D:\BUILD PHASE 2\P-008\lms-simulator"
Copy-Item .env.example .env
# Thay PACEWISE_API_KEY và PACEWISE_LAUNCH_SECRET trong .env bằng chuỗi ngẫu nhiên.
docker compose up --build -d
```

Mở <http://localhost:8010>. Swagger UI: <http://localhost:8010/docs>.

| Vai trò | Email | Mật khẩu |
|---|---|---|
| Sinh viên | `student@canvas.local` | `demo123` |
| Giảng viên | `teacher@canvas.local` | `demo123` |

```powershell
docker compose ps
docker compose logs -f app
docker compose down
```

Database và file upload nằm trong Docker volumes. Chỉ chạy lệnh sau khi thật sự
muốn xoá toàn bộ dữ liệu để seed lại:

```powershell
docker compose down -v
```

## Bảo mật

- Đăng nhập phát hành opaque session token ngẫu nhiên; database chỉ lưu SHA-256
  hash của token.
- Trình duyệt nhận cookie `HttpOnly`, `SameSite=Lax`; thao tác ghi bằng cookie
  yêu cầu CSRF token.
- Middleware đối chiếu mọi `user_id`/`sender_id` cũ với session đang đăng nhập,
  nên client không thể mạo danh người khác.
- Quyền course được kiểm tra qua enrollment và vai trò student/instructor.
- PaceWise dùng API key server-to-server riêng, không dùng session của sinh viên.
- Launch token được ký HMAC, hết hạn sau 5 phút và chỉ dùng một lần.

Đổi `SESSION_COOKIE_SECURE=true` khi chạy HTTPS. Không commit file `.env`.

## API dành cho PaceWise

Gửi header sau ở mọi endpoint `/api/pacewise/v1/*`:

```text
X-PaceWise-Key: <PACEWISE_API_KEY>
```

Các endpoint chính:

| Endpoint | Dữ liệu |
|---|---|
| `GET /api/pacewise/v1/courses` | Courses; có thể lọc theo `user_id` |
| `GET /courses/{id}/enrollments` | Thành viên, vai trò và tiến độ |
| `GET /courses/{id}/assignments?user_id=` | Assignment group, deadline hiệu lực, unlock/lock, rubric |
| `GET /courses/{id}/submissions` | Lịch sử attempt, nhiều file, comment, reassigned/excused |
| `GET /courses/{id}/modules?user_id=` | Prerequisite, completion rule và tiến độ item |
| `GET /courses/{id}/content` | Syllabus, pages, quizzes, outcomes... |
| `GET /courses/{id}/files` | Version/checksum/folder/access scope cho RAG |
| `GET /courses/{id}/sections` | Lớp học phần và thành viên |
| `GET /courses/{id}/groups` | Group set, group và thành viên |
| `GET /courses/{id}/analytics` | Participation, active time và page/module view |
| `GET /users/{id}/planner` | To-do cá nhân và assignment-linked planner item |
| `GET /courses/{id}/appointment-groups` | Slot tư vấn và reservation |
| `GET /courses/{id}/grades` | Điểm hiện tại và lịch sử chấm |
| `GET /courses/{id}/quizzes` | Câu hỏi và lượt làm bài |
| `GET /courses/{id}/outcomes` | Outcome và alignment |
| `GET /learning-evidence` | Bằng chứng mức độ hiểu bài |
| `GET /events?after_id=N` | Event outbox để đồng bộ tăng dần |
| `GET /audit-logs?after_id=N` | Nhật ký hành động |

Ví dụ:

```powershell
$key = (Get-Content .env | Select-String '^PACEWISE_API_KEY=').Line.Split('=', 2)[1]
curl.exe -H "X-PaceWise-Key: $key" http://localhost:8010/api/pacewise/v1/courses
curl.exe -H "X-PaceWise-Key: $key" "http://localhost:8010/api/pacewise/v1/events?after_id=0"
```

`events` là durable outbox. PaceWise lưu ID cuối đã xử lý rồi gọi lại với
`after_id`, nhờ đó có thể đồng bộ bù nếu tiến trình nhận sự kiện bị gián đoạn.

## Canvas extensions phục vụ PaceWise

- Deadline được phân giải theo thứ tự ưu tiên: `student > group > section > default`.
- Assignment group hỗ trợ trọng số, drop điểm thấp/cao và nhiều grading type.
- Module có prerequisite, completion requirement và progress riêng từng sinh viên.
- Mỗi lần nộp tạo một immutable attempt; một attempt có thể chứa tối đa 10 file.
- Rubric gồm criterion/rating và assessment theo từng criterion, không chỉ JSON tự do.
- Tài liệu RAG có version, SHA-256 checksum, folder và access scope theo course,
  section, group hoặc user.
- Analytics và Planner là dữ liệu riêng, không suy diễn từ giao diện phía client.

## Launch từ Canvas sang PaceWise

Simulator có hai điểm vào dùng cùng một secure launch flow:

- **Global Navigation → PaceWise** mở dashboard đa môn. Một course enrollment được
  dùng làm ngữ cảnh ban đầu; backend PaceWise sau đó xác minh và nạp toàn bộ course
  mà người dùng được phép truy cập.
- **Course Navigation → PaceWise** mở ứng dụng với course hiện tại được chọn sẵn,
  phù hợp cho hỏi đáp và đánh giá hiểu bài theo môn.

Người dùng nhấn **PaceWise** hoặc **Open PaceWise**; simulator tạo launch token chứa
đúng `user`, course khởi đầu và `role`, rồi chuyển đến:

```text
<PACEWISE_URL>/launch?token=<signed-token>
```

Backend PaceWise xác thực và tiêu thụ token bằng:

```http
POST /api/pacewise/v1/launch/verify
X-PaceWise-Key: ...
Content-Type: application/json

{"token":"..."}
```

Đây là cơ chế launch an toàn cho MVP. Khi tích hợp Canvas thật, thay bằng LTI
1.3/OIDC nhưng giữ nguyên contract nội bộ của PaceWise.

## Dữ liệu đánh giá

Seeder tạo 24 sinh viên evaluation trên nhiều course, assignment, bài nộp đúng
hạn/muộn, grade history, rubric, quiz response và hơn 100 learning-evidence
samples. Seeder idempotent: restart container không nhân đôi cohort.

Tài khoản evaluation dùng mật khẩu `demo123` và email dạng
`evaluation001@canvas.local`.

## Phạm vi

Simulator phục vụ tích hợp PaceWise, không phải bản phân phối Canvas đầy đủ.
Canvas thật vẫn nằm tại `../canvas-lms` để đối chiếu UI và API. Mã nguồn Canvas
LMS được phát hành theo GNU AGPL v3; hãy giữ thông tin license và attribution khi
tái sử dụng mã nguồn hoặc tài sản.
