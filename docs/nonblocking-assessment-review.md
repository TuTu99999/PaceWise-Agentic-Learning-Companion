# Assessment verification và human review không chặn học

Scope sản phẩm giữ nguyên **Plan → Do → Reflect**. Assessment là sub-agent trong Do;
human review là đường xử lý ngoại lệ, không phải phase hoặc điều kiện mở khóa Plan.

## Luồng triển khai

```text
Câu trả lời → đánh giá + kiểm tra rubric/evidence
  ├─ Hợp lệ, đủ tin cậy → lưu evidence → cập nhật Knowledge State có điều kiện
  ├─ Chưa chắc, còn câu đã duyệt → câu khác cùng KC và cùng mức
  ├─ Vẫn chưa chắc / không còn câu phù hợp → pending_review
  └─ Kết quả chấm không hợp lệ → abstained, không kết luận sinh viên yếu

pending_review → sinh viên vẫn tiếp tục Do / Reflect / Plan
  ├─ Giảng viên xem lại → evidence gates → Knowledge State
  └─ Bằng chứng độc lập mới đủ điều kiện → superseded + audit, không duyệt kết luận cũ
```

### Giới hạn kiểm chứng

- Tối đa **hai câu bổ sung do uncertainty trong một checkpoint**, không phải hai câu
  mỗi lần reload hoặc mỗi item. Đây là policy khởi đầu, chưa phải ngưỡng được
  calibration với sinh viên thật.
- Chỉ chọn câu đã duyệt, đúng KC và cùng stage; không tái dùng question fingerprint.
- Counter, hint và retry receipt thuộc server. Reload/retry không làm tăng lượt.
- Khi bank thiếu câu phù hợp, không tự sinh câu chưa duyệt hoặc nâng mức hiểu.
- Lỗi provider trả 503, không tạo evidence học tập, không tiêu hao lượt và có thể
  gửi lại cùng retry key. Kết quả malformed không tạo ca misconception giả.
- Hỗ trợ sau một câu đã được chấm sai tin cậy vẫn đi theo policy remediation hiện có;
  không phải mọi câu sai đều gửi giảng viên.

### Hai lớp trạng thái

Knowledge State/snapshot lưu những gì đã có bằng chứng. Evidence và checkpoint
lưu riêng `review_status`: `accepted`, `verifying`, `pending_review`, `abstained`.
`pending_review` không phải mức hiểu và không đồng nghĩa với `no_evidence` hay yếu.

Trong lúc kiểm chứng/chờ duyệt:

- Không ghi đè snapshot hoặc hồ sơ kiến thức đã xác nhận bằng kết luận tạm thời.
- Reflect giữ riêng evidence đáng tin gần nhất và evidence chưa xác nhận;
  một câu đang chờ duyệt không che mất quan sát đáng tin trước đó của cùng phiên.
- Không dùng evidence tạm thời để tăng estimate hoặc trigger knowledge-gap re-plan.
- Những sự kiện thật như bỏ lỡ phiên, deadline/capacity thay đổi vẫn được xử lý.
- UI ghi rõ mức tạm thời và quyền tiếp tục học; chỉ checkpoint kết luận bị dừng,
  không khóa phiên học, Reflect hoặc Plan.

### Human review và bằng chứng mới

- Chờ lâu **không tự duyệt**, không có timeout chuyển pending thành mastered.
- Chỉ bằng chứng mới được chấp nhận, không dùng hint trong app, chứng minh đạt
  đúng dimension mới có thể giải quyết ca. Không sửa kết quả evidence cũ.
- Auto-resolution giới hạn cùng institution/student/course/checkpoint/stage;
  không giải quyết ca khác hoặc quyết định đã được giảng viên duyệt/bác bỏ.
- Ca chưa kết thúc (`pending`, `in_review`, `needs_evidence`) có thể thành
  `superseded`; lưu evidence ID mới, timestamp, reason và event audit.
- API từ chối duyệt lại ca superseded (409). Projection không để action cũ mở lại ca.
- Một câu hỏi dùng ở hai study block không được gộp rồi ghi đè bằng chứng chờ duyệt.
- Teacher review và learner updates dùng row locks. Kiểm chứng concurrency
  PostgreSQL tải thực tế chưa nằm trong lượt evaluation này.
- Kết luận của giảng viên vẫn phải qua evidence gates; không phát minh transfer
  hoặc retention chưa được kiểm tra. Không có endpoint Assessment tự áp dụng lịch.

## Phân chia code

| Thành phần | Trách nhiệm |
|---|---|
| `src/services/assessment_review_policy.py` | Pure deterministic policy; giới hạn câu và điều kiện Plan được sử dụng evidence |
| `src/api/adaptive_assessment.py` | Đánh giá, chuẩn bị decision trước persistence, transaction cho một attempt |
| `src/services/adaptive_assessment.py` | State machine, câu kế tiếp, counter, scope và giải quyết ca bằng evidence mới |
| `src/services/agent_memory.py` | Evidence/snapshot persistence, chỉ tạo human case khi thực sự escalation |
| `src/services/replan_policy.py` | Cả phản tư phiên và tuần bỏ qua kết luận chưa xác nhận |
| `src/services/plan_intelligence.py` | Không chuyển mức hiểu provisional thành trọng số readiness |
| `AdaptiveDoCheckpoint.tsx` | Thông báo kiểm chứng, chờ duyệt, abstention và quyền tiếp tục học |

Không thêm table hoặc phase; dùng JSON contracts và event log hiện có. Không xóa
hoặc tự phê duyệt ca cũ trong DB. Các ca legacy cần giảng viên hoặc bằng chứng có
scope phù hợp; policy lọc hợp đồng evidence có flags cập nhật đều false.

## Evaluation kỹ thuật

Các case chạy bằng SQLite riêng/in-memory, ASGI HTTP API, LLM fixtures xác định
và React DOM tests. Đây **không phải đánh giá độ chính xác chấm của provider thật**
hoặc bằng chứng cải thiện kết quả học tập.

| Case | Output được assertion kiểm tra |
|---|---|
| Kết quả confidence thấp, có câu khác | `verification_required`, `review.status=verifying`, không có human case |
| Hai câu bổ sung vẫn chưa chắc | `verification_count=2`, `review_required`, một case `pending` |
| Reload/retry | Cùng state/receipt, không tăng counter hoặc tạo thêm case |
| Giảng viên không duyệt 14 ngày | Case vẫn pending; `blocks_planning=false`, `blocks_learning=false` |
| Đã có kế hoạch xác nhận | Block cũ không bị sửa; mastery trước uncertainty giữ nguyên |
| Pending có confidence cao và dimension failed | Session/weekly re-plan đều `keep`, không tăng readiness risk |
| Có phiên bỏ lỡ thật trong lúc pending | Vẫn `propose_draft`, `auto_apply=false`, cần sinh viên xác nhận |
| Bằng chứng độc lập mới đạt | Sang stage tiếp; ca của đúng checkpoint thành `superseded`, giữ kết luận cũ |
| Giảng viên duyệt ca superseded | HTTP 409, không lưu decision mới |
| Malformed output | `abstained`, không tạo review case, không tạo snapshot mới |
| Provider timeout | HTTP 503, chưa chấm, không tiêu hao lượt, retry hoạt động |
| Delayed probe thiếu tin cậy | Probe vẫn pending; snapshot giữ `transfer`, không ghi nhận `retained` |
| Hai block dùng cùng câu | Hai case độc lập, không ghi đè checkpoint context |
| Status và rubric của model mâu thuẫn | `verifying`, reason `contradictory_evaluation` |

JUnit regression: `evals/reports/nonblocking-review-backend-2026-10-09.xml` và
`evals/reports/nonblocking-review-frontend-2026-10-09.xml`.

Kết quả chạy cuối ngày 2026-10-09:

- Backend: **448 passed**, 0 failed (`pytest tests`, database SQLite test riêng).
- Frontend: **165 passed**, 40 test files (`vitest run`).
- `ruff check src tests`: **pass**.
- `npm run build`: **pass**; main JS chunk 342.85 kB (gzip 108.69 kB), không có
  cảnh báo chunk >500 kB.
- Đã sửa lỗi autoflush phát hiện bởi regression: action của giảng viên được thêm
  sau validation trạng thái ca; request 409 không tạo action duyệt.

```powershell
# Chạy từ root repo; không dùng DB demo/production cho pytest.
$env:DATABASE_URL = 'sqlite:///./tmp/review-policy-test-20261009.db'
.\.venv\Scripts\python.exe -m pytest tests -q --junitxml=evals/reports/nonblocking-review-backend-2026-10-09.xml
.\.venv\Scripts\python.exe -m ruff check src tests

# Chạy frontend trong terminal khác.
cd frontend/pacewise
npm test
npm run build
```

## Vận hành và giới hạn

- Chưa rebuild/restart Docker trong lượt này; thay đổi là source code và test.
- Chưa chuyển hàng chờ thành card trong Tổng quan lớp; tab human review hiện có
  được giữ nguyên, thêm trạng thái đã có bằng chứng mới.
- Chưa làm thứ tự ưu tiên queue theo deadline: cần xác định mapping KC → task
  còn mở và quyền hiển thị trước khi thêm score ưu tiên.
- Chưa triển khai kiểm chứng bằng câu LLM tự sinh; bank phải có câu phù hợp được duyệt.
- Chưa chạy live provider mới/pilot hoặc đo false mastery/kappa với nhãn chuyên gia.
- Lượt xác nhận sau: provider fixtures adversarial bổ sung → PostgreSQL concurrency
  → pilot giảng viên/sinh viên và calibration ngưỡng/câu hỏi.
