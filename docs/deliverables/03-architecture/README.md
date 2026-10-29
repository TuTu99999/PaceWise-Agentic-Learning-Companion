# 3. Architecture diagram

Sơ đồ kiến trúc đầy đủ và data flow:
[`../../architecture_diagram.md`](../../architecture_diagram.md).

## Tổng quan hệ thống

```mermaid
flowchart LR
    Student["Student browser"] --> Web["React / Nginx"]
    Teacher["Instructor browser"] --> Web
    Web --> API["FastAPI API"]
    API --> Auth["Session · CSRF · RBAC"]
    API --> Graph["LangGraph coordinator"]
    Graph --> Agents["Plan · Do · Assessment · Recover · Reflect"]
    Agents --> LLM["OpenAI-compatible LLM"]
    API <--> DB[("PostgreSQL")]
    API <--> Vector[("Qdrant")]
    Worker["Sync / RAG worker"] <--> DB
    Worker <--> Vector
    API <--> LMS["Course source / LMS API"]
    Worker <--> LMS
    API <--> Calendar["Google Calendar"]
```

## Luồng Plan tương lai và prerequisite

```mermaid
flowchart TD
    A["Assignment chưa quá deadline"] --> B["Đưa vào kế hoạch dài hạn"]
    L["Kết thúc buổi học liên quan"] --> E["earliest_start_at"]
    B --> S["Scheduler"]
    E --> S
    S --> D["Do block không sớm hơn earliest_start_at"]
    D --> G{"Mở phiên sau prerequisite?"}
    G -->|Không| W["Thông báo chờ buổi học"]
    G -->|Có| R["Bắt đầu Do"]
    R --> C["Learn / Self-check evidence"]
    C --> P["Đánh dấu Plan cần phân tích lại"]
```

Sơ đồ chi tiết còn có agent graph, sequence Plan → Do → Reflect, LMS sync/RAG,
data ownership, security boundary và deployment map.
