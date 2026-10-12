# PaceWise — Project Charter

**Đội:** P-008 · **Thời gian thực hiện:** 5 tuần · **Cập nhật:** 24/09/2026

## 1. Mục đích

Trong 5 tuần, đội xây một MVP triển khai online cho một môn pilot và 3–5 đơn vị kiến thức. Sản phẩm phải chứng minh được chu trình **Plan–Do–Reflect**, trong đó bước Do có cơ chế kiểm tra mức hiểu bài và phục hồi kế hoạch.

Đầu ra cuối kỳ không chỉ là demo giao diện. Đội phải cung cấp:

- sản phẩm chạy end-to-end cho sinh viên và giảng viên;
- Canvas fixture bắt buộc, REST read-only khi có credential, LTI 1.3 là P1;
- guardrail và RAG có nguồn;
- ba bộ đánh giá, mỗi bộ ít nhất 120 mẫu;
- logging, metrics, tracing, load test, runbook và bằng chứng deploy.

## 2. Phạm vi và tiêu chí thành công

### P0

- Đăng nhập và RBAC hai vai trò.
- Plan từ assignment/deadline/quỹ thời gian.
- Do với cập nhật tiến độ, RAG có nguồn, kiểm tra nhanh và Recover.
- Reflect cuối tuần.
- Dashboard giảng viên tổng hợp với ngưỡng n≥5.
- Human-in-the-loop cho lưu kế hoạch, đổi lịch, duyệt rubric và hỗ trợ cá nhân.
- Production-like deployment với health check, monitoring và rollback.

### P1

- Canvas REST thật nếu có sandbox/token.
- LTI 1.3 nếu có developer key.
- Memory dài hạn, model routing nâng cao và load test 1.000 concurrent users.

### Không làm

- Không làm hộ/nộp bài/chấm điểm chính thức.
- Không fork Canvas, không triển khai toàn trường.
- Không mở rộng quá một môn và 3–5 đơn vị kiến thức trước khi P0 đạt release gate.

### Mục tiêu pilot

- Tỷ lệ nộp đúng hạn tăng ≥10 điểm phần trăm so với baseline.
- ≥70% ca nguy cơ còn khả thi có phương án phục hồi được xác nhận trước deadline.
- Trung vị sai số ước lượng giảm ≥20% sau ba tuần.
- ≥60% bằng chứng học tập dẫn tới hành động tiếp theo.

Đây là mục tiêu cần đo, không phải kết quả đã đạt.

## 3. Thành viên và quyền sở hữu

| Thành viên | Vai trò | Quyền sở hữu | Đầu ra chịu trách nhiệm |
|---|---|---|---|
| **Phạm Khắc Tú** | Tech Lead | Kiến trúc, backend, Canvas, bảo mật, hạ tầng | FastAPI, data model, adapter Canvas, RBAC, CI/CD, deploy, observability |
| **Nguyễn Gia Khánh** | AI Engineer | AI harness và đánh giá | LangGraph, Plan/Recover, RAG/Qdrant, reranker, guardrail, diagnosis, ba bộ eval |
| **Trần Thế Anh** | Product Owner | Scope, trải nghiệm sinh viên, nghiệm thu | Backlog, acceptance criteria, frontend Student Experience, analytics, UAT, demo |
| **Thân Thị Kim Chi** | Business Analyst | Nội dung học tập và trải nghiệm giảng viên | Môn pilot, objective/rubric, fixture, frontend Management Console, dữ liệu/QA |

Mỗi hạng mục có một người chịu trách nhiệm cuối cùng, nhưng PR bắt buộc có reviewer khác người viết.

## 4. RACI

Ký hiệu: **R** thực hiện, **A** chịu trách nhiệm cuối, **C** tham vấn, **I** được thông báo.

| Workstream | Tech Lead | AI Engineer | PO | BA |
|---|---:|---:|---:|---:|
| Scope, backlog, release | C | C | A/R | C |
| Kiến trúc và API contract | A/R | C | C | I |
| Canvas fixture/REST/LTI | A/R | C | I | R |
| Google Calendar và `.ics` | A/R | I | R | C |
| Plan/Recover workflow | C | A/R | R | C |
| RAG và guardrail | C | A/R | C | R |
| Đánh giá hiểu bài | C | R | C | A/R |
| Student Experience | C | C | A/R | C |
| Management Console | C | C | C | A/R |
| Eval và load test | R | A/R | C | R |
| Privacy/security | A/R | C | C | R |
| Observability/deploy | A/R | R | C | I |
| UAT/demo/tài liệu | C | C | A/R | R |

## 5. Kế hoạch 5 tuần

### Tuần 1 — Khóa hợp đồng và dựng nền

**Mục tiêu:** một vertical slice rỗng nhưng deploy được.

- PO + BA chốt môn pilot, 3–5 đơn vị kiến thức, personas và acceptance criteria.
- BA chuẩn bị Canvas fixture, objective, rubric nháp và tìm SME duyệt.
- Tech Lead dựng schema, RBAC, API contract, CI/CD, staging và OpenTelemetry.
- AI Engineer dựng LangGraph skeleton, model gateway, Qdrant và harness eval.
- Cả đội tạo baseline cho ba bộ dữ liệu; mỗi bộ đạt ít nhất 40/120 mẫu.

**Mốc cuối tuần:** đăng nhập hai vai trò, fixture load được, health check và staging chạy; các quyết định mở có owner/hạn.

### Tuần 2 — Plan và theo dõi Do

**Mục tiêu:** sinh viên tạo, xác nhận và theo dõi một kế hoạch tuần.

- Tech Lead: assignment API, plan persistence, audit/idempotency, adapter Canvas REST sau feature flag và xuất `.ics` không cần OAuth.
- AI Engineer: task decomposition, constraint validator, risk rules và prompt/version logging.
- PO: màn S0–S5, loading/error/empty state, event tracking.
- BA: Management Console skeleton, fixture edge cases, review milestone/output.
- Eval `planning_v1` đạt 120 mẫu và chạy trong CI.

**Mốc cuối tuần:** Plan end-to-end; kế hoạch vô nghiệm được báo đúng; không ghi DB trước xác nhận.

### Tuần 3 — Recover, RAG và hiểu bài

**Mục tiêu:** khép vòng từ sai lệch/bằng chứng đến hành động.

- Tech Lead: snapshot/diff/recovery API, ingestion pipeline, retention job.
- AI Engineer: Recover, retriever/reranker, classifier liêm chính học thuật, output policy, check/diagnosis schema và độ tin cậy.
- PO: màn cảnh báo, xác nhận Recover, tutor, guardrail và kết quả hiểu bài.
- BA: duyệt bộ 1–3 câu cho mỗi đơn vị kiến thức; phối hợp hai annotator và người phân xử.
- Hoàn tất `grounding_safety_v1` và `understanding_journey_v1`, mỗi bộ ≥120 mẫu.

**Mốc cuối tuần:** risk → Recover → xác nhận hoạt động; tutor có nguồn; ca không chắc chắn được chuyển hàng chờ.

### Tuần 4 — Reflect, giảng viên và hardening

**Mục tiêu:** chạy trọn Plan–Do–Reflect cho hai vai trò.

- Tech Lead: privacy threshold n≥5, Google OAuth/Calendar, rate limit, cache, dashboards, alert và backup/restore drill.
- AI Engineer: Reflect routing, RAGAS, LLM-as-Judge calibration, cost/latency report.
- PO: Reflect, màn hình kết nối/tải lịch, accessibility/responsive và UAT sinh viên.
- BA: dashboard, hàng chờ giảng viên, luồng xác nhận và UAT giảng viên/SME.
- Nếu credential đã sẵn sàng và P0 ổn: bật REST read-only; LTI chỉ làm sau đó.

**Mốc cuối tuần:** staging feature-complete, ba suite đạt ngưỡng hoặc có bug list rõ, privacy test pass.

### Tuần 5 — Đánh giá, tải và release

**Mục tiêu:** tạo bằng chứng có thể lặp lại và phát hành.

- Chạy full regression, security/permission tests và 100 virtual users.
- Đo p50/p95/error rate/token/cost/cache hit/model route.
- Fix theo mức nghiêm trọng; đóng scope P1 nếu ảnh hưởng P0.
- Production deploy, smoke test, alert test và rollback rehearsal.
- QA toàn bộ docs, link, Mermaid, chính tả, thuật ngữ và thông tin đội.
- Thu demo, lập báo cáo metric và checklist release.

**Mốc cuối tuần:** production URL, tag release, dashboard quan sát, eval report, runbook và demo end-to-end.

## 6. Cách làm việc

### Nhánh và PR

- `main`: luôn deploy được; chỉ nhận PR từ `develop`.
- `develop`: nhánh tích hợp.
- Nhánh ngắn hạn: `feat/*`, `fix/*`, `docs/*`, `test/*`, `chore/*`.
- Không giữ nhánh theo tên người xuyên suốt dự án.
- Mỗi PR giải quyết một mục tiêu, có mô tả thay đổi/lý do/cách test.
- Ít nhất một reviewer khác người viết; thay đổi auth/privacy/eval cần đúng owner review.

### Nhịp đội

- Daily 15 phút: đã làm, sẽ làm, blocker.
- Thứ Hai: chốt mục tiêu và capacity tuần.
- Thứ Tư: demo nội bộ vertical slice, cắt scope sớm nếu trễ.
- Thứ Sáu: review metric, retro và cập nhật quyết định.
- Quyết định thay stack/scope được ghi trong ADR hoặc PRD cùng PR code.

## 7. Definition of Ready và Done

### Ready

- Có user story và acceptance criteria.
- Có owner/reviewer và dependency.
- Có API/data contract hoặc mock.
- Có rủi ro quyền riêng tư/HITL nếu liên quan.
- Có cách test và event cần ghi.

### Done

- Code review và CI pass.
- Unit/integration/e2e phù hợp đã viết.
- Có loading, empty, error, timeout và permission state.
- Logging/tracing không lộ secret hoặc nội dung thô không cần thiết.
- Docs/API/schema được cập nhật cùng PR.
- Có bằng chứng test hoặc ảnh/video trên staging.
- Product owner nghiệm thu theo acceptance criteria.

## 8. Kế hoạch đánh giá

| Bộ | Owner chính | Reviewer | Quy mô | Chạy |
|---|---|---|---:|---|
| `planning_v1` | AI Engineer | Tech Lead + PO | ≥120 | CI nightly/full release |
| `grounding_safety_v1` | AI Engineer | BA + Tech Lead | ≥120 | CI nightly/full release |
| `understanding_journey_v1` | BA + AI Engineer | SME + PO | ≥120 | trước release và khi đổi rubric/model |

Ngưỡng chi tiết nằm trong PRD. Không được giảm sample dưới 120 để “làm đẹp” metric. Mọi báo cáo ghi dataset version, model, prompt, commit và ngày chạy.

## 9. Rủi ro

| Rủi ro | Tín hiệu sớm | Phương án |
|---|---|---|
| Không có Canvas credential | Chưa nhận trước cuối tuần 1 | Dùng fixture; REST/LTI chuyển P1 |
| Thiếu SME | Rubric chưa duyệt | Chỉ demo câu đóng đã kiểm tra; không tuyên bố diagnosis mở |
| Scope phình | P0 chưa xong nhưng mở thêm môn/LTI | PO đóng P1, giữ 1 môn và 3–5 đơn vị |
| Model chậm/đắt | p95/cost vượt ngân sách | cache, model nhỏ, timeout, giảm context |
| Guardrail chặn nhầm | false positive >10% | tách rule/classifier, review lỗi, sửa threshold |
| Chẩn đoán sai | high-confidence error >5% | hạ ngưỡng, từ chối kết luận, chuyển giảng viên |
| Lộ dữ liệu | dashboard n<5/log raw | fail release, tắt feature, xoay secret nếu cần |
| Thành viên nghẽn | ticket blocked >1 ngày | pair, chia ticket nhỏ, đổi owner |

## 10. Governance và release

Quyết định còn mở phải chốt đúng owner/hạn trong PRD. Tech Lead có quyền dừng release vì bảo mật, mất dữ liệu hoặc SLO; PO dừng vì sai scope/happy path; BA dừng vì rubric/dữ liệu chưa hợp lệ; AI Engineer dừng vì eval dưới ngưỡng mà không có fallback.

Trước production phải có:

- migration và rollback đã thử;
- secret/config tách khỏi repo;
- health/readiness check;
- dashboard latency/error/token/cost;
- alert và runbook;
- backup/restore test;
- smoke test hai vai trò;
- báo cáo ba bộ eval;
- QA docs và demo.

## 11. Tài liệu liên quan

- [Yêu cầu đề tài](./00-topic-requirements.md)
- [Brief](./01-brief.md)
- [PRD](./02-prd.md)
- [Wireframe/UI Flow](./03-wireframe-uiflow.md)
- [Architecture](./architecture_diagram.md)
