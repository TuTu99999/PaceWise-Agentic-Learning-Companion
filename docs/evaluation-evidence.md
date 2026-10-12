# Evaluation evidence — 04/10/2026

Cập nhật 10/10: [Demo một web — LMS Docker nội bộ](pacewise-only-demo-evaluation-2026-10-10.md) — 684 backend, 319 frontend, 87 simulator tests pass; browser thật hai role login/data/logout pass, không request web LMS. Giữ nguyên database/uploads; chưa deploy cloud.

Cập nhật 10/10: [Nhịp cá nhân theo môn và hoạt động](activity-rhythm-evaluation-2026-10-10.md) — 659 backend, 305 frontend test pass; 16 browser checks. Xác nhận preference không tự đổi plan, chưa có pilot để khẳng định hiệu quả học.

KPI cập nhật ngày 09/10: [Kế hoạch ban đầu/hiện tại + evidence + so sánh nộp đúng hạn](learning-kpis-evaluation-2026-10-09.md) — backend 593, frontend 220 test pass; đã rebuild Docker và kiểm tra HTTP hai role. Không coi timer là bằng chứng, không tạo lịch sử tiến độ trước PaceWise giả.

Kết quả cập nhật ngày 09/10: [Tổng quan giảng viên + Google Calendar pool/cache/export](teacher-overview-calendar-evaluation-2026-10-09.md) — backend 560, frontend 217 test pass; có Docker/PostgreSQL HTTP smoke cho hai role. Các số liệu phía dưới là evidence lịch sử ngày 04/10.

Đây là bằng chứng **được chạy lại trên code hiện tại**, không tái sử dụng kết luận của bản 03/10. Các case dưới đây được kích hoạt thủ công bằng CLI/HTTP/SQL và ghi lại output thực tế.

## Kết luận nhanh

| Nhóm | Kết quả |
|---|---:|
| Docker/HTTP health | PASS |
| Lưu lịch cá nhân qua reload | PASS |
| Workspace PostgreSQL integration | PASS |
| Plan/Do/Tracking/Recover/Reflect workflows | PASS — 36/36 |
| RAG + guardrail | PASS — 33/33 |
| Dữ liệu Toán rời rạc + PDF | PASS |
| Frontend full test | PASS — 95/95 |
| Production build | PASS |



## Môi trường

- Ngày chạy: `2026-10-04`, múi giờ `Asia/Ho_Chi_Minh`.
- Docker services: frontend, backend, worker, LMS Simulator, hai PostgreSQL và Qdrant.
- Backend health trả `checkpoint=postgres`.
- Frontend: Vitest `v3.2.7`; production build bằng TypeScript + Vite `v6.4.3`.

## EV-01 — Full stack và endpoint sống

**Mục tiêu:** xác nhận các component bắt buộc đang chạy và frontend/backend/LMS phản hồi thật.

**Lệnh:**

```powershell
docker compose ps
curl.exe -sS http://localhost:8000/health
curl.exe -sS http://localhost:8000/api/v1/status
curl.exe -sS http://localhost:8010/api/health
curl.exe -sS -o NUL -w "frontend_status=%{http_code} content_type=%{content_type}" http://localhost:5173/
```

**Output thực tế:**

```text
backend             Up (healthy)
frontend            Up (healthy)
lms-postgres        Up (healthy)
lms-simulator       Up (healthy)
pacewise-postgres   Up (healthy)
qdrant              Up
worker              Up

{"status":"ok","env":"development","checkpoint":"postgres"}
{"status":"ready","agent":"PaceWise LangGraph Agent v1.0"}
{"status":"ok","service":"lms-simulator"}
frontend_status=200 content_type=text/html
```

**Kết quả:** PASS.

## EV-02 — Ăn/Ngủ/Bận còn sau reload

**Mục tiêu:** regression test lỗi thao tác lịch cá nhân chỉ nằm trong state màn hình.

**Input:** lưu hai slot `Ăn tối 18:00–18:45` và `Ngủ 23:00–24:00`, tạo state mới như sau reload rồi hydrate workspace.

**Lệnh:**

```powershell
cd frontend\pacewise
npm.cmd test -- --run tests/workflow-state.test.ts -t "round-trips personal schedule slots through workspace hydration after reload"
```

**Output thực tế:**

```text
✓ tests/workflow-state.test.ts (13 tests | 12 skipped)
Test Files  1 passed (1)
Tests       1 passed | 12 skipped (13)
```

**Kết quả:** PASS. UI hiện dispatch `SAVE_AVAILABILITY` khi thêm, resize hoặc xóa; AppStore tự lưu workspace lên backend và `HYDRATE_WORKSPACE` khôi phục dữ liệu khi reload. Bản AI draft cũ không còn ghi đè lịch cá nhân mới.

## EV-03 — Workspace thật sự lưu ở PostgreSQL

**Mục tiêu:** kiểm chứng backend không chỉ trả state trong memory, đồng thời xử lý version conflict.

**Lệnh:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api/test_lms_integration.py::test_switch_course_and_persist_workspace -q
```

**Output thực tế:**

```text
.                                                                        [100%]
1 passed in 0.32s
```

**Kết quả:** PASS. Case thực hiện login/session, đổi course scope, PUT/GET workspace và kiểm tra optimistic version.

## EV-04 — Workflow Plan/Do/Recover/Reflect

**Mục tiêu:** kiểm chứng graph routing, structured output, deadline/capacity constraints, HITL confirmation và quality gate.

**Lệnh:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agents/test_workflows.py -q
```

**Output thực tế:**

```text
....................................                                     [100%]
36 passed in 0.54s
```

**Kết quả:** PASS — 36/36. Đây là deterministic workflow evidence; chưa thay thế pilot với người học thật.

## EV-05 — Do: RAG/citation và chống làm hộ

**Mục tiêu:** xác nhận retrieval/citation validation và guardrail không phụ thuộc lời nhắc UI.

**Lệnh:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agents/test_rag_tools.py tests/test_agents/test_guardrails.py -q
```

**Output thực tế:**

```text
.................................                                        [100%]
33 passed in 0.49s
```

**Kết quả:** PASS — 33/33. Bao phủ nguồn hợp lệ, thiếu nguồn, prompt injection và yêu cầu làm hộ bài tính điểm.

## EV-06 — Dữ liệu demo Toán rời rạc và quiz Chương 3

**Mục tiêu:** xác nhận LMS hiện dùng môn `DS201 — Toán rời rạc`, module Chương 3 và quiz đúng chủ đề.

**Truy vấn read-only:**

```sql
SELECT qc.title AS quiz, count(q.id) AS questions
FROM courses c
JOIN course_content qc ON qc.course_id=c.id AND qc.kind='quiz'
LEFT JOIN quiz_questions q ON q.quiz_id=qc.id
WHERE c.code='DS201' AND qc.title ILIKE '%Quan hệ%'
GROUP BY qc.id,qc.title;
```

**Output thực tế:**

```text
quiz                                | questions
------------------------------------+----------
Quiz Chương 3: Quan hệ hai ngôi     | 5
(1 row)
```

Truy vấn module cũng trả:

```text
DS201 | Toán rời rạc | Chương 3: Quan hệ hai ngôi
```

**Kết quả:** PASS.

## EV-07 — PDF học liệu mở được trong Do

**Mục tiêu:** xác nhận tài liệu `TRR_Full_P4.pdf` được LMS phục vụ như PDF thật.

**Lệnh:**

```powershell
curl.exe -sS -I http://localhost:8010/static/mock-files/TRR_Full_P4.pdf
```

**Output thực tế:**

```text
HTTP/1.1 200 OK
content-type: application/pdf
accept-ranges: bytes
content-length: 519716
```

**Kết quả:** PASS. `accept-ranges` cho phép trình duyệt/PDF viewer tải theo phần khi cuộn.

## EV-08 — Frontend regression suite và production build

**Mục tiêu:** kiểm tra thay đổi persistence không phá calendar, Do, Recover, Reflect, accessibility hoặc build.

**Lệnh:**

```powershell
cd frontend\pacewise
npm.cmd test -- --run
npm.cmd run build
```

**Output thực tế sau bản sửa:**

```text
Test Files  27 passed (27)
Tests       95 passed (95)

vite v6.4.3 building for production...
✓ 103 modules transformed.
dist/assets/index-*.js      335.72 kB │ gzip: 106.60 kB
dist/assets/PlanPage-*.js    43.42 kB │ gzip:  13.60 kB
✓ built
```

**Kết quả:** PASS. Bundle chính không còn cảnh báo chunk vượt 500 kB.

## Cách tái lập

```powershell
docker compose up --build -d
docker compose ps
.\.venv\Scripts\python.exe -m pytest tests/test_agents/test_workflows.py tests/test_agents/test_rag_tools.py tests/test_agents/test_guardrails.py -q
cd frontend\pacewise
npm.cmd test -- --run
npm.cmd run build
```

## Giới hạn của evidence

### Bổ sung 10/10/2026 — nhiệm vụ quá hạn và clock Plan

Đã tách overdue chưa hoàn thành khỏi capacity tương lai, chuyển UI Plan sang giờ thật và sửa serializer UTC của LMS simulator. Lịch sử/evidence vẫn giữ để Reflect và cá nhân hóa có điều kiện; không coi qua hạn là đã học xong. Phạm vi, test và giới hạn bằng chứng ở [Expired planning evaluation](expired-planning-evaluation-2026-10-10.md).

### Bổ sung 10/10/2026 — xác nhận phần lịch hợp lệ

Đã tách capacity shortfall khỏi lỗi ca học: cho review/xác nhận phần được backend kiểm tra, giữ phần việc thiếu và cảnh báo; không bỏ qua deadline/dependency, không tự giảm estimate. Lịch đang dùng không bị bản nháp thay thế trước xác nhận. Kết quả regression và browser, cùng giới hạn fixture/pilot, nằm ở [Partial plan confirmation evaluation](partial-plan-confirmation-evaluation-2026-10-10.md).

### Bổ sung 10/10/2026 — bỏ thao tác lịch trùng

Đã bỏ nút/menu “Thêm vào lịch”, form ca tự học thừa và dropdown ưu tiên cá nhân; giữ panel hiện có và lịch đã lưu. **659 backend / 306 frontend / 31 calendar browser checks pass**. Chi tiết phạm vi và lỗi Settings 320px ngoài phạm vi nằm ở [Student calendar simplification](student-calendar-simplification-2026-10-10.md).

### Bổ sung 10/10/2026 — nhịp học và độ tin cậy phiên

Đã thêm timer checkpoint backend, retry/version chống trùng, Reflect ngắn, đề xuất nhịp bằng rule có nguồn và xác nhận, scheduler giữ tổng công việc và tính nghỉ/checkpoint. Estimate không pooling lịch sử khác bài/môn hay tăng thời lượng từ gián đoạn. Báo cáo, acceptance tests, output và giới hạn pilot nằm ở [Study rhythm evaluation](study-rhythm-evaluation-2026-10-10.md).

### Bổ sung 09/10/2026 — học liệu do LMS quản lý

Đã kiểm thử tự động lifecycle upload PDF → đồng bộ/index → cập nhật → thu hồi quyền → xóa, cùng UI trạng thái và proxy PDF. **411 backend / 159 frontend / 14 LMS simulator tests pass**. Các ca, raw JUnit và giới hạn nằm ở [LMS materials sync evaluation](lms-materials-sync-evaluation.md). Đây không phải manual browser evidence hoặc xác nhận Canvas production.

- Các test trên chứng minh logic và integration chạy đúng với fixture/simulator hiện tại; chưa chứng minh KPI nộp đúng hạn ngoài thực tế.
- Chưa chạy tải 1000 sinh viên; phạm vi demo hiện tại chỉ cần kiểm tra vài phiên đồng thời.
- Cần pilot nhiều tuần và SME review để đánh giá chất lượng kế hoạch, citation và phản tư trong điều kiện thật.
