# Adaptive Do Assessment — nghiệm thu kỹ thuật và giới hạn

Ngày: 2026-10-08, Asia/Saigon. Sản phẩm vẫn Plan → Do → Reflect.
Assessment chỉ là sub-agent bên trong Do; không có tab/phase thứ tư.

## Đã bổ sung

| Thiếu sót cũ | Implementation mới |
|---|---|
| Chấm từng câu riêng | Session server-owned; policy Recall → Explain → Why → Apply → Transfer |
| Hint là bộ đếm client | H1–H5 persisted, retry idempotent; nội dung giảng viên duyệt hoặc process scaffold |
| Rubric định tính mơ hồ | Diagnostic criterion 0–4 có mô tả và quote; mọi tiêu chí phải đủ, không average |
| Level kế thừa từ metadata | Dimension/prerequisite gate deterministic; closed đúng chỉ recognition |
| Có retained nhưng không kiểm tra trì hoãn | Probe có due date, baseline, unseen item, cùng user/course/KC; retained_level riêng |
| Hypothesis thành fact | Approved taxonomy + lexical retrieval/rerank; suspected/unknown và teacher queue |
| Re-plan churn | Threshold, duplicate/cooldown guard, diff preview; không auto apply |
| Re-plan mất lịch cũ | Preserve elapsed/completed và ongoing; không bỏ history do task không được chọn |
| Reflect đọc nhầm checkpoint | Timer metrics không bị assess ghi đè; phản tư block đọc evidence cùng block/course |

## Chuẩn bị dữ liệu để demo thật

1. Giảng viên duyệt KC trong cấu trúc môn và gắn KC đó vào các câu hỏi.
2. Ngân hàng câu hỏi LMS cần đủ Recall, Explain, Why, Application, Transfer cho KC được demo.
3. Trong trang sửa câu hỏi, chọn stage, rubric và tối đa 5 hints. Explain/Why/Apply/Transfer phải là câu mở.
4. Chuẩn bị thêm item mới ở Application/Transfer để dùng delayed probe. Hai ID cùng text không là item mới.
5. Thiếu item: UI báo coverage gap; không tự phát hành câu LLM chưa duyệt. Có thể tiếp tục học/Reflect.
6. Model timeout: HTTP 503, giữ nguyên câu/lượt thử và cho retry; không tạo evidence chấm sai. Rubric malformed: abstain/teacher review, không nâng Knowledge State.

## Contract và audit

- `POST /api/v1/do/assessment/start`: start/resume, option restart/probe_id; enrollment và ownership scoped.
- `POST /api/v1/do/assessment/{id}/hint`: event_key idempotent, H1–H5 do server giữ.
- `POST /api/v1/do/assessment/{id}/answer`: rubric version/checkpoint stage do server giữ; response max 5000 chars.
- `GET /api/v1/do/assessment/due?course_id=...`: chỉ probe của learner/course đang được phép.
- Start/answer/hint không sửa calendar. Assessment evidence và session state được commit cùng transaction.
- Hint success chuyển sang item chưa thấy cùng stage; fail có remediation, rồi stop. Restart explicit chọn item mới.
- Teacher review có evidence v2 phải đi qua cùng evidence gates, lưu evidence mới thay vì sửa record gốc.
- LearningEvent ghi start, hint, assessment, Knowledge State, Reflect và quyết định/proposal/confirm Plan.
- Policy threshold mặc định là heuristic cần calibration, không phải kết luận nghiên cứu.

## Các scenario tự động đã thực thi

Đây là API/component tests, **không phải manual browser test hoặc dữ liệu người học thật**.

| Scenario | Output được assert |
|---|---|
| Đi hết 5 stage bằng item đã duyệt | completed, transfer; 5 evidence; resume/retry không duplicate |
| Gợi ý và client cố gửi hint_level=0 | Server vẫn H1; first_attempt=false; chọn item khác cùng stage |
| Model dimensions nói passed nhưng criterion reasoning score=1 | Không tiến stage; no_evidence; remediation/stop |
| Thiếu Explain item được duyệt | coverage_gap=explain; mức trước vẫn recognition |
| Probe chưa tới hạn | HTTP 409, chưa retained |
| Probe tới hạn, đúng KC, item chưa dùng, không hint | retained với baseline level; probe passed |
| User/course khác hoặc reused key khác response | 404/409; không đọc/ghi evidence người khác |
| Prompt injection | 422 trước evaluator |
| Model timeout rồi hồi phục | 503, giữ câu/lượt thử; cùng retry key gửi lại thành công, không tạo evidence lỗi |
| Rubric đổi version/revoked | 409; resume reset kiểm chứng, không giữ stale pass |
| Re-plan với tín hiệu nhỏ hoặc lặp | keep, auto_apply=false |
| Drift đủ lớn | propose_draft, requires_confirmation=true |
| Lịch quá khứ của task bỏ chọn | Block history vẫn giữ nguyên |

## Evaluation artifacts và cách chạy

### Kết quả chạy cuối ngày 2026-10-08

| Kiểm tra | Kết quả thực tế | Artifact |
|---|---|---|
| Full backend regression | 354 passed, 0 failures/errors | [Backend JUnit](../evals/reports/adaptive-backend-2026-10-08.xml) |
| Frontend component/unit tests | 119 passed, 33 test files | [Frontend JUnit](../evals/reports/adaptive-frontend-2026-10-08.xml) |
| TypeScript / production build | Pass; entry JS 344.98 kB, gzip 109.18 kB | Output `npm run typecheck` và `npm run build` |
| Ruff / whitespace | Pass | `ruff check --no-cache` và `git diff --check` |
| Adaptive offline evaluation | 60 unique cases, tất cả engineering gates pass | [Offline report](../evals/reports/adaptive-offline-2026-10-08.json) |
| Live grading | Provider timeout; 0 responded cases; agreement null | [Live attempt report](../evals/reports/adaptive-assessment-2026-10-08.json) |

Backend chạy trên SQLite test riêng, không dùng dữ liệu learner production. API chain sử dụng approved bank
fixture và mock evaluator; vì thế output `transfer`/`retained` trong test chứng minh gate/state-machine,
không chứng minh LLM chấm đúng người học thật. Đã sửa regression test thu hồi item để nhắm đúng
item đang hiển thị sau reset; item cũ không còn là câu active. Closed recall dùng deterministic evaluator,
nên test model outage thực thi ở stage Explain thay vì giả định Recall luôn gọi LLM.

```powershell
$env:DATABASE_URL='sqlite:///./tmp/adaptive-validation.db'
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests -q
.venv\Scripts\python.exe -m ruff check --no-cache src tests scripts/evaluate_adaptive_assessment.py scripts/probe_assessment_model.py
.venv\Scripts\python.exe scripts/evaluate_adaptive_assessment.py
# Cần credential/provider hoạt động; chỉ gửi 8 developer-authored mathematical cases:
.venv\Scripts\python.exe scripts/evaluate_adaptive_assessment.py --live-model
cd frontend/pacewise
npm run typecheck
npm test -- --reporter=dot
npm run build
```

Báo cáo: [adaptive-assessment-2026-10-08.json](../evals/reports/adaptive-assessment-2026-10-08.json).
60 boundary cases **unique**, không nhân bản cùng case để tăng sample count. Metric là gate/policy accuracy,
không phải khả năng chẩn đoán sinh viên. Các metric parser cũ vẫn giữ để compatibility nhưng đã chú thích semantics.

### Live-model blocker

Đã thử bộ 8 câu với provider được cấu hình; provider timeout, mọi kết quả abstain.
Connectivity probe trả `OpenAITimeoutError`, HTTP status không có. Lượt báo cáo lại có timeout bounded
và dừng sau 2 lỗi liên tiếp: `provider_unavailable`, 0 responded cases; label agreement là null.
Không tính abstain ở câu sai thành chấm đúng. Cần provider hoạt động rồi rerun để đánh giá rubric thật.
Không tự sửa `.env` hay thay model/endpoint của người dùng.

Lưu ý script offline có thể ghi đè report mặc định. Để giữ artifact live lỗi và tạo report offline mới,
dùng `--output evals/reports/adaptive-offline-2026-10-08.json`.

## Chưa được chứng minh / chưa nghiệm thu production

- Chưa có independent SME labels, Cohen kappa, misconception F1, confidence calibration hoặc pilot.
- Lexical rerank là MVP baseline; chưa fine-tune misconception model hay semantic ranker cho taxonomy.
- Chưa chứng minh learning gain/on-time submission improvement hoặc transfer/retention của sinh viên thật.
- Test DB SQLite, chưa load-test PostgreSQL concurrent retry, migration rollout hoặc multi-worker races.
- Không kiểm tra browser end-to-end/Docker deployment trong lượt này; không tự publish/approve câu demo lên LMS.
- Lịch lớp/LMS tiếp tục là ràng buộc cố định, không bị Assessment/Reflect sửa.
- Phase 6–7 cần người học/thầy cô và dữ liệu thật; không coi synthetic eval là thay thế.

Trạng thái đúng: **offline engineering validation; live grading blocked by provider timeout; not learner-validated**.
