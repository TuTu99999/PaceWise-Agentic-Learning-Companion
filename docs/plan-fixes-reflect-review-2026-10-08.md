# Plan fixes và review Reflect — 2026-10-08

Scope: sửa deadline tới phút, hard quality gate và estimate-driven proposal; sau đó **review** Reflect.
Assessment vẫn nằm trong Do. Không sửa `.env`, push Git, publish LMS hay rebuild Docker trong lượt này.

## 1. Plan: các thay đổi đã triển khai

### Deadline chính xác

- [planning_time.py](../src/services/planning_time.py): deadline timestamp được chuyển sang timezone lịch;
  timestamp không có timezone được hiểu theo timezone ứng dụng. Deadline chỉ có ngày nghĩa là hết ngày đó.
- Scheduler ưu tiên deadline theo timestamp, không chỉ theo ngày; cắt capacity và block theo phút hạn nộp.
- Date-only deadline vẫn cho block kết thúc `24:00`. Timestamp `00:00` không cho học sau đầu ngày đó.
- Quality evaluator kiểm tra độc lập end timestamp của block; các block history không bị sửa.

Case lỗi cũ:

```text
now: 2026-10-08 10:00 GMT+7
deadline: 2026-10-08 12:00 GMT+7
availability: 17:00–21:00
before: block 17:00–18:00, feasible=true, quality=100
after: blocks=[], shortfalls=[{taskId:a1, missingMin:60}], canConfirm=false
```

### Quality gate tại preview và commit

- `canConfirm` chỉ phụ thuộc hard constraints: deadline, capacity, block time/overlap, dependency và task hợp lệ.
- P80 shortfall, rubric/provenance coverage gap là warning để SV xem và chấp nhận; không được gọi là bản
  đã qua mọi tiêu chí (`releaseReady=false`). Rubric coverage ở đây là mapping metadata, không chứng minh
  milestone thực sự đáp ứng rubric về mặt nội dung học thuật.
- Backend lưu `pending_plan_draft` trong LearnerMemory do server quản lý. Client workspace/current_plan
  không thay thế được proposal dùng để xác nhận.
- Khi xác nhận, refresh LMS thay vì dùng projection cache; kiểm tra deadline mới và thời điểm hiện tại.
- Preview ID không khớp proposal hiện tại: HTTP 409. Retry cùng ID sau khi commit: trả lại kết quả đã xác nhận,
  không tạo confirm event/history lần nữa.
- [PlanPage](../frontend/pacewise/src/pages/student/PlanPage.tsx) khóa nút áp dụng và save handler khi có hard error.

Case regression:

```text
capacity đủ + dependency unknown → canConfirm=false, HTTP 409 trước agent call
P50 đủ + P80 thiếu → canConfirm=true, ROBUST_CAPACITY_RISK warning
deadline đổi sau lúc preview → commit refresh LMS, HTTP 409 nếu block vượt deadline mới
client gửi current_plan hợp lệ nhưng server draft sai → vẫn HTTP 409
retry confirm cùng draft ID → HTTP 200, cùng confirmed_plan
confirm preview cũ sau khi có proposal mới → HTTP 409
```

### Estimate điều khiển proposal, không ghi đè student input

- Milestone estimate được tính một lần từ allocation baseline, tránh nhân personal factor hai lần.
- Target trong **bản đề xuất** dùng `max(baseline, estimated P50)`; không tự rút ngắn dưới lượng việc SV xác nhận.
- `remainingMin` gốc và lịch đang áp dụng giữ nguyên. Chỉ áp dụng lịch/thời lượng mới sau confirmation.
- `durationAdjustments` hiển thị student minutes, baseline và proposed minutes ngay trên UI.
- P80 dùng để kiểm tra buffer/capacity risk, không tự tăng lịch lên P80.

```text
SV nhập: 60 phút
3 phiên trước: planned=60, actual=120
personal factor bounded: 1.75
P50 heuristic: 105 phút; P80 heuristic: 135 phút
proposal scheduled: 105 phút (không còn 60 phút)
input remainingMin: vẫn 60; requiresConfirmation=true
```

P50/P80 là estimate heuristic chưa được calibration thành quantile thống kê trên dữ liệu learner thật.

## 2. Kết quả verification

| Kiểm tra | Kết quả / evidence |
|---|---|
| Backend regression | **372 passed** — [JUnit](../evals/reports/plan-fixes-backend-2026-10-08.xml) |
| Frontend regression | **125 passed**, 34 files — [JUnit](../evals/reports/plan-fixes-frontend-2026-10-08.xml) |
| Typecheck / production build | Pass |
| Ruff / git diff --check | Pass |
| Engineering eval | 60 unique adaptive boundary cases, legacy/adaptive gates pass — [JSON](../evals/reports/plan-fixes-engineering-2026-10-08.json) |

Các regression mới ở [test_plan_safety.py](../tests/test_services/test_plan_safety.py),
[test_routes.py](../tests/test_api/test_routes.py) và
[planConfirmation.test.ts](../frontend/pacewise/src/utils/planConfirmation.test.ts).

Backend test sử dụng SQLite riêng; không ghi learner workspace production. Chưa browser E2E, PostgreSQL concurrent
confirm/load test hay triển khai container. Các bộ test là engineering verification, không chứng minh educational outcome.

## 3. Review tổng thể Reflect

### Phần đúng hướng

- Có phản tư activity và weekly; UI trả về lịch, re-plan chỉ tạo proposal chờ xác nhận.
- Không trực tiếp ghi mastery/Knowledge State; dữ liệu này thuộc Assessment trong Do.
- Có clamp planning signal, block/course-scoped evidence cho phản tư phiên, audit, duplicate/cooldown guard.
- Early weekly reflect có cảnh báo dữ liệu đến hiện tại. Clock demo cố định không phải clock production.
- Live smoke qua 9router localhost, model `cx/gpt-5.6-sol`, một case phiên tổng hợp: **21.1 giây**,
  `awaiting_student`, pending `save_activity_reflection`; không có assessment/knowledge-write keys.
  AI nhìn đúng 60 phút dự kiến, 100 phút thực tế, hoàn thành 50%, đề xuất bước tiếp theo.
  Đây là một smoke case, không phải evaluation toàn bộ Reflect hoặc SME agreement.

### Các vấn đề đã tái hiện, chưa sửa trong scope review này

#### R1 — Evidence Reflect chưa được ground độc lập

[reflect.py](../src/agents/workflows/reflect.py) cho `evidence` do model trả về ghi đè dữ liệu gốc.
Fixture evaluator trả `planned_minutes=999` khi input là 60; draft giữ **999**.
Re-plan policy đọc records riêng nên không đồng nghĩa mọi số giả sẽ thay đổi lịch, nhưng bản phản tư/dữ liệu audit
không nên trình bày dữ kiện AI tạo thành quan sát thực tế.

Hướng sửa: facts immutable từ session/LMS; student self-report tách riêng; AI chỉ bổ sung explanation và
evidence references. Reject/flag số liệu không tồn tại trong records và giữ source IDs.

#### R2 — Weekly re-plan dùng phiên/evidence cuối, chưa tổng hợp cả tuần

[agent_memory.py](../src/services/agent_memory.py) dùng `last_do_session` và `last_assessment_evidence`
cho weekly policy. History trước đó vẫn có trong prompt, nhưng deterministic decision không aggregate history.

Case in-memory thực thi:

```text
earlier block: missed, planned=60, actual=0, completion=0%
last block: completed, planned=60, actual=60, completion=100%
weekly signal: missed_block
decision: keep, reasons=[risk_below_threshold]
```

Một phiên cuối ổn không đủ bác bỏ rủi ro của các phiên trước. Cần aggregate đúng tuần/course/task,
đối chiếu remaining workload/deadline; không chỉ lấy lần quan sát cuối. Weekly UI đa môn cũng cần
backend aggregate các course memories/evidence tương ứng thay vì chỉ active-course memory.

#### R3 — Cause schema không đồng nhất giữa Reflect và Plan

```text
Reflect normalized cause: missing_prerequisite
Plan adapter normalized cause: none
followUpMinutes: vẫn 30
```

Reflect dùng `missing_prerequisite`, `task_harder_than_expected`, `interruption`, `estimate_error`;
Plan adapter dùng `knowledge_gap`, `underestimated`, `schedule_conflict`, `distraction`...
Factor/follow-up có thể còn truyền được, nhưng nguyên nhân/audit mất ý nghĩa.

Hướng sửa: một shared typed cause contract/version và explicit mapping cho dữ liệu legacy;
không âm thầm đổi mọi unknown cause thành `none`. Áp dụng signal đúng thời gian hiệu lực và KC/task liên quan.

## Kết luận

**Cập nhật lượt sửa tiếp theo:** R1/R2/R3 bên trên đã được sửa và kiểm thử;
xem [Reflect fixes evaluation](reflect-fixes-evaluation-2026-10-08.md).
Phần tái hiện bên trên được giữ làm bằng chứng trước sửa; không còn là trạng thái
hiện tại của ba lỗi này.

Ba lỗi Plan được sửa và có regression. **Reflect activity đã có nền tảng tốt, nhưng chưa thể gọi toàn bộ
Reflect ổn**: cần ưu tiên factual grounding, weekly aggregation rồi thống nhất signal schema.
