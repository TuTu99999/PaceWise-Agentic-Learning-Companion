# PaceWise — AI workflows, kiểm thử và đánh giá

**Phiên bản:** `2026-09-28.v1`  
**Phạm vi:** Coordinator và sáu workflow Plan, Tracking, QA, Understanding, Recover, Reflect.

## 1. Luồng chạy chuẩn

```mermaid
flowchart TD
    A[Request + PaceWise session] --> B[Coordinator]
    B --> C{Guardrail xác định}
    C -->|Prompt injection| X[Chặn an toàn]
    C -->|Yêu cầu làm hộ| Q[QA guided_help]
    C -->|Hợp lệ| R{Route workflow}
    R --> P[Plan]
    R --> T[Tracking]
    R --> Q2[QA + RAG]
    R --> U[Understanding]
    R --> V[Recover]
    R --> F[Reflect]
    P --> G[Quality Gate]
    T --> G
    Q2 --> G
    U --> G
    V --> G
    F --> G
    G --> C2{Output hợp lệ?}
    C2 -->|Không, lần đầu| RP[Repair Agent: safe correction]
    RP --> G
    C2 -->|Có hoặc đã repair 1 lần| D{Workflow outcome}
    D -->|Plan| H1{Sinh viên xác nhận?}
    D -->|Recover| H2{Sinh viên xác nhận?}
    D -->|Reflect| H3{Sinh viên xác nhận?}
    D -->|Understanding| H4{Đủ rubric, bằng chứng, độ tin cậy?}
    D -->|Tracking / QA| O[Output]
    H4 -->|Không| I[Hàng chờ giảng viên]
    H4 -->|Có| O
    I --> O
    H1 --> O
    H2 --> O
    H3 --> O
    X --> O
    Q --> O
```

Coordinator chạy rule nhanh trước, gọi semantic classifier theo cấu hình và áp output policy trước khi trả kết quả. Specialist luôn đi qua Critic; output lỗi được chuyển sang Repair Agent rồi Critic kiểm tra lại đúng một lần. Giới hạn một lần repair tránh vòng lặp agent vô hạn và giữ latency dự đoán được. Khi intent rõ, bộ định tuyến xác định được ưu tiên để giảm latency và tránh phụ thuộc cách diễn đạt của LLM. Mỗi node ghi audit event chỉ gồm tên node, workflow, kết quả, latency và thời gian; không ghi prompt thô.

## 2. Hợp đồng của từng workflow

| Workflow | Input chính | Validator bắt buộc | Output/HITL |
|---|---|---|---|
| Plan | assignment, availability, unavailable slot | thời lượng, capacity, ID, dependency, cycle | bản nháp; chỉ áp dụng sau xác nhận |
| Tracking | deadline, estimated hours, current time | phép tính slack và overlap theo ngày/timezone | risk signal; đề nghị Recover nếu có nguy cơ |
| QA | query, course_id, tài liệu môn | course filter, retrieval score, citation khớp passage | trả lời có nguồn; từ chối khi thiếu nguồn |
| Understanding | câu trả lời + `assessment_id`; backend lấy rubric/đáp án đã duyệt từ LMS | trạng thái, evidence, confidence, rubric | kết quả hỗ trợ; ca không chắc được ghi bền vững vào hàng chờ giảng viên |
| Recover | plan hiện tại, milestone, assignment | ít nhất hai phương án, đủ schema, bảo vệ deadline | snapshot + phương án; chưa sửa lịch trước xác nhận |
| Reflect | progress metrics, lịch sử tuần | draft có điều hiệu quả, nguyên nhân, một điều chỉnh, evidence | điều chỉnh tuần sau; chỉ áp dụng sau xác nhận |

API dùng PaceWise session trong cookie `HttpOnly` và bắt buộc CSRF cho request ghi dữ liệu. Backend tự lấy `user_id`, vai trò và môn đang chọn từ session; `thread_id` được dựng theo `institution:user:course:learning-cycle`. Working memory theo tuần được tách khỏi learner memory dài hạn theo `institution:user:course`. Client không được tự chọn danh tính, rubric, đáp án hoặc phạm vi course. Worker duy trì LMS projection để chat đọc snapshot nội bộ; học liệu thô được ingest bất đồng bộ và request QA chỉ retrieval từ namespace Qdrant đã phân quyền. Lỗi nội bộ không được trả nguyên văn cho client.

## 3. Test tự động

Chạy toàn bộ test và lint:

```powershell
python -m ruff check src/ evals/ tests/
python -m pytest tests/ -q --cov=src --cov-fail-under=80
cd frontend/pacewise
npm test
npm run test:e2e
```

Test bao phủ routing, Critic–Repair, guardrail, prompt injection, yêu cầu làm hộ, RAG theo course, citation, plan constraint, overlap/timezone, HITL, rubric, assessment escalation, recovery, reflection, xác thực PaceWise, Google Calendar, LMS client, phân quyền course và API. Frontend có Vitest + Testing Library, kiểm tra accessibility bằng axe-core và smoke test trình duyệt bằng Playwright.

CI dùng `pytest-cov` làm cổng chính thức và sẽ fail nếu line coverage của toàn bộ package `src` dưới 80%. Con số pass/coverage phải lấy từ run CI gần nhất, không ghi cứng một baseline đã cũ vào tài liệu.

Toàn bộ dependency Python của backend, LMS simulator, test, eval và load test được quản lý tập trung trong `requirements.txt`. Hai Dockerfile chỉ cài section runtime tương ứng để tránh đưa pytest/RAGAS/Locust hoặc AI stack vào image không cần chúng. Adapter vector vẫn được kiểm thử bằng fake module; kiểm thử tích hợp Qdrant thật phải chạy ở job/service riêng.

## 4. Eval định lượng

Chạy:

```powershell
python -m evals.run_agent_eval
python -m evals.run_agent_eval --output evals/reports/latest.json
python -m evals.run_safety_eval
```

Ba dataset chính đều có 120 mẫu; routing có thêm 120 mẫu hỗ trợ và bộ adversarial tĩnh có 100 mẫu. Kết quả baseline đã lưu tại `evals/reports/deterministic-2026-09-28.json`.

Guardrail có thêm `safety_adversarial_v1.jsonl` gồm 100 mẫu tĩnh độc lập với regex trong code,
bao phủ tiếng lóng, Anh–Việt, yêu cầu gián tiếp, prompt injection trong tài liệu và intent hỗn hợp.
Safety eval có gọi semantic classifier nên chỉ báo cáo kết quả khi chạy bằng model credential thật;
CI mặc định chỉ xác minh schema, số mẫu và các unit test của ba lớp policy.

| Metric | Ngưỡng P0 | Baseline xác định |
|---|---:|---:|
| Plan đúng ràng buộc | ≥95% | 100% |
| Recover bảo vệ deadline | ≥90% | 100% |
| Risk recall | ≥85% | 100% |
| Risk precision | ≥75% | 100% |
| Quyết định citation hợp lệ | ≥95% | 100% |
| Integrity recall | ≥95% | 100% |
| Chặn nhầm yêu cầu hợp lệ | ≤10% | 0% |
| Diagnosis macro-F1 | ≥0,80 | 1,00 |
| Lỗi diagnosis độ tin cậy cao | ≤5% | 0% |
| Routing accuracy | theo dõi | 100% |

### RAGAS trên dữ liệu pilot

`evals/run_ragas_eval.py` nhận JSONL tối thiểu 100 mẫu có bốn trường
`user_input`, `response`, `retrieved_contexts`, `reference`, sau đó tính
faithfulness, answer relevancy, context precision và context recall. Đây là eval tùy chọn cần
credential của model judge; không chạy trong CI xác định và không được báo cáo là đã đạt khi chưa
có dataset pilot được SME gán nhãn.

```powershell
pip install -r requirements.txt
python evals/run_ragas_eval.py evals/datasets/rag-pilot.jsonl
```

### Độ đồng thuận SME và sai số safety

`evals/run_pilot_eval.py` yêu cầu tối thiểu 100 mẫu, hai nhãn độc lập, một nhãn đã
adjudicate và output AI. Runner báo Cohen's Kappa, quadratic weighted Kappa cho mức
hiểu bài, safety precision/recall, false-positive và false-negative. File
`pilot-human-template.jsonl` chỉ là schema minh họa, không phải bằng chứng pilot.

```powershell
python evals/run_pilot_eval.py evals/datasets/pilot-human-v1.jsonl
```

### Load test và quan sát hệ thống

```powershell
pip install -r requirements.txt
locust -f load_tests/locustfile.py --host http://localhost:5173 --headless -u 1000 -r 50 -t 5m --csv evals/reports/load-1000
docker compose --profile observability up -d
```

Backend xuất request ID, structured log và Prometheus metrics cho HTTP, agent node, RAG,
LLM call, token và chi phí ước tính (khi cấu hình đơn giá model).
Prometheus scrape `/metrics`; Grafana tự provision dashboard `PaceWise Overview`. Kịch bản 1.000
virtual users chỉ là acceptance profile: phải chạy trên staging đủ tài nguyên và lưu report trước
khi tuyên bố đạt tải.

## 5. Cách hiểu đúng kết quả

Kết quả 100% chỉ chứng minh các rule/validator hiện tại vượt bộ fixture tổng hợp đã version hóa; không chứng minh model đạt 100% ngoài đời. Không dùng test set để sửa prompt.

Trước production pilot vẫn bắt buộc:

- Thu thập `pilot-human-v1.jsonl` ≥100 mẫu; hai SME gán nhãn độc lập, adjudicate bất đồng rồi chạy `run_pilot_eval.py`.
- Chạy RAGAS/faithfulness với tài liệu pilot thật và hiệu chuẩn LLM-as-Judge bằng nhãn người.
- Test Qdrant thật, Postgres checkpointer, timeout/retry và model provider thật.
- Chạy load test 100 virtual users; chỉ tuyên bố 1.000 concurrent khi có bằng chứng.
- Security review cho rate limit, secret manager, quyền course/role và retention dữ liệu.

Vì vậy trạng thái hiện tại là **deterministic AI harness đã qua unit/eval**, chưa phải bằng chứng đủ để tuyên bố production-ready.
