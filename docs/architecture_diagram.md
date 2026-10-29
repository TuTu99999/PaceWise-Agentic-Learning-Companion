# PaceWise architecture and data flow

Tài liệu này mô tả kiến trúc đang chạy trong repository, không phải kiến trúc dự kiến. Mốc kiểm chứng: **18/10/2026**.

## 1. Component diagram

```mermaid
flowchart LR
    subgraph Client["Browser"]
        UI["React + TypeScript\nPlan · Do · Reflect"]
        Instructor["Instructor UI\nOverview · Question design"]
    end

    subgraph PaceWise["PaceWise"]
        Nginx["Nginx frontend\n:5173"]
        API["FastAPI API\n:8000"]
        Auth["Session + CSRF + RBAC"]
        Graph["LangGraph coordinator"]
        Specialists["Plan · Do · Tracking · QA\nUnderstanding · Recover · Reflect"]
        Gate["Quality gate + one repair pass"]
        Worker["LMS projection / RAG worker"]
        DB[("PaceWise PostgreSQL\n:5433")]
        Vector[("Qdrant\n:6333")]
    end

    subgraph LMS["Canvas-compatible LMS Simulator"]
        LMSAPI["LMS API + launch\n:8010"]
        LMSDB[("LMS PostgreSQL\n:5434")]
        Files["Course files / PDF"]
    end

    subgraph External["Optional external services"]
        LLM["OpenAI-compatible LLM"]
        GCal["Google Calendar"]
    end

    UI --> Nginx
    Instructor --> Nginx
    Nginx -->|"/api/* reverse proxy"| API
    API --> Auth
    Auth --> Graph
    Graph --> Specialists --> Gate
    Gate -->|"pass or repair once"| Graph
    Graph --> LLM
    API <--> DB
    Worker <--> DB
    Worker <--> Vector
    API --> Vector
    API <--> LMSAPI
    Worker <--> LMSAPI
    LMSAPI <--> LMSDB
    LMSAPI --> Files
    API <--> GCal
```

## 2. Agent graph

```mermaid
flowchart TD
    Request["Authenticated request + LMS/workspace context"] --> Coordinator
    Coordinator -->|plan| Plan
    Coordinator -->|do| Do
    Coordinator -->|tracking| Tracking
    Coordinator -->|qa| QA
    Coordinator -->|understanding| Understanding
    Coordinator -->|recover| Recover
    Coordinator -->|reflect| Reflect
    Plan --> QualityGate
    Do --> QualityGate
    Tracking --> QualityGate
    QA --> QualityGate
    Understanding --> QualityGate
    Recover --> QualityGate
    Reflect --> QualityGate
    QualityGate -->|passed| Response
    QualityGate -->|failed, first time| Repair
    Repair --> QualityGate
    QualityGate -->|failed after repair| SafeResponse["Safe failure / human decision"]
```

`LearningGraphState` mang theo assignment, module, lịch rảnh/bận, kế hoạch hiện tại, hồ sơ học tập, nguồn truy xuất, risk, phương án Recover và bản nháp Reflect. Runtime Docker dùng PostgreSQL checkpointer; unit test có thể dùng memory checkpointer.

## 3. Plan → Do → Reflect

```mermaid
sequenceDiagram
    actor S as Sinh viên
    participant LMS as LMS
    participant UI as PaceWise UI
    participant API as FastAPI / LangGraph
    participant DB as PostgreSQL
    participant Q as Qdrant

    LMS-->>API: course, assignment, quiz, lịch học, submission
    API-->>UI: snapshot đã phân quyền
    S->>UI: thêm Ăn/Ngủ/Bận/Tự học, ưu tiên và giờ sinh hoạt
    UI->>DB: PUT workspace (version + CSRF)
    S->>UI: AI lập kế hoạch
    UI->>API: goal + workload + availability + constraints + earliest_start_at
    API-->>UI: milestone + study block + capacity + assumptions
    S->>UI: xem trước, chỉnh, Áp dụng kế hoạch
    UI->>DB: lưu plan đã xác nhận
    S->>UI: mở study block
    UI->>API: kiểm tra block đã qua earliest_start_at
    UI->>API: bắt đầu/kết thúc Do, actual time, blocker
    API->>Q: retrieval học liệu đã ingest
    Q-->>API: passages có metadata nguồn
    API-->>UI: gợi ý tài liệu / trả lời có citation hoặc từ chối
    UI->>DB: session + evaluation
    S->>UI: trả lời Self-check đã được giảng viên thiết kế
    UI->>API: câu trả lời tự luận
    API->>DB: assessment signal có cấu trúc
    API-->>UI: đánh dấu phần lịch tương lai cần phân tích lại
    S->>UI: Reflect sau hoạt động hoặc cuối tuần
    UI->>API: plan so với actual + câu trả lời phản tư
    API-->>UI: tóm tắt + một điều chỉnh đề xuất
    alt cần điều chỉnh
        UI-->>S: quay về Plan với bản AI đề xuất
        S->>UI: xem và xác nhận
    else không cần điều chỉnh
        UI-->>S: quay về lịch học hiện tại
    end
```

## 4. Lưu lịch cá nhân sau reload

```mermaid
flowchart LR
    Drag["Thêm/kéo/resize/xóa\nĂn · Ngủ · Bận · Tự học"] --> Local["PlanPage state"]
    Local --> Action["SAVE_AVAILABILITY"]
    Action --> Store["AppStore workspace state"]
    Store -->|"debounce 750 ms"| Put["PUT /api/v1/workspace"]
    Put -->|"optimistic version check"| PG[("pacewise_workspaces")]
    Reload["Reload / đăng nhập lại"] --> Get["GET /api/v1/workspace"]
    Get --> Hydrate["HYDRATE_WORKSPACE"]
    PG --> Get
    Hydrate --> Calendar["Khôi phục các ô lịch cá nhân"]
```

Workspace là nguồn dữ liệu chính cho lịch cá nhân, routine, plan, session và reflection. LMS vẫn là nguồn chính cho môn học, deadline, lịch lớp và submission. Bản `planDraft` chỉ là đề xuất AI và không được ghi đè lịch cá nhân mới hơn.

## 5. LMS sync và RAG

```mermaid
flowchart TD
    Event["LMS integration event"] --> Worker
    Worker --> Cursor["Durable sync cursor"]
    Worker --> Projection["Course / learner projection"]
    Worker --> Job["RAG ingestion job"]
    Job --> Extract["Đọc nội dung text LMS"]
    Extract --> Chunk["Chunk + source metadata"]
    Chunk --> Qdrant
    LMSFiles["LMS sở hữu file, phiên bản, ACL"] --> Manifest["File manifest + checksum"]
    Manifest --> Worker
    Worker --> FileIndex["LmsFileIndex: metadata + text/chunks\nKhông lưu binary"]
    FileIndex --> FileJob["Pending / Retry / Index / Thu hồi"]
    FileJob --> Qdrant
    API --> LiveACL["Manifest theo user, đọc live"]
    LiveACL --> Retrieval["Filter course + file ID + phiên bản"]
    Retrieval --> Qdrant
    API --> PDFProxy["Proxy PDF có session + ACL\nprivate, no-store"]
    PDFProxy --> LMSFiles
    SSE["SSE lms.changed"] --> Browser["Frontend refresh snapshot"]
    Projection --> API
    API --> Browser
```

- Worker xử lý event theo cursor và hàng đợi bền vững, nên restart không làm mất vị trí đồng bộ.
- Chat không ingest tài liệu trong request; nó chỉ truy xuất corpus đã chuẩn bị.
- Nếu evidence không đạt ngưỡng, QA phải báo thiếu nguồn thay vì tạo citation giả.
- File LMS được index riêng; cleanup snapshot nội dung text không xóa vector file. Metadata/ACL được đọc lại ở mỗi request để loại phiên bản cũ và file bị thu hồi trước khi đưa nội dung vào LLM.
- Giao diện upload/sửa/xóa/phân quyền chỉ có trên LMS. PaceWise giảng viên chỉ có trạng thái đồng bộ ở Tổng quan lớp; rubric/KC phục vụ Assessment không bị xóa theo tab nạp dữ liệu.

## 6. Data ownership và bảo mật

| Dữ liệu | Nguồn chính | Quy tắc |
|---|---|---|
| Course, assignment, quiz, deadline, submission | LMS PostgreSQL/API | PaceWise đọc theo enrollment/session; không cho client tự chọn user/role |
| Lịch cá nhân, routine, plan, study session, reflection | PaceWise PostgreSQL | Lưu theo `user_id`; PUT yêu cầu CSRF và version để phát hiện conflict |
| Trạng thái hội thoại agent | LangGraph PostgreSQL checkpointer | Tách theo thread/session đã xác thực |
| Chunk học liệu và metadata nguồn | Qdrant | Chỉ ingest từ course context được phép |
| Tổng quan lớp | Projection tổng hợp | Instructor-only; ngưỡng nhóm tối thiểu, không dùng để xếp hạng/chấm điểm |
| Google token | PaceWise backend | Mã hóa server-side; không trả refresh token xuống browser |

Session dùng cookie `HttpOnly`; request thay đổi trạng thái cần CSRF. Service key giữa PaceWise và LMS không được đóng gói vào frontend.

## 7. Deployment map

| Service | Port host | Vai trò |
|---|---:|---|
| `frontend` | 5173 | Nginx phục vụ React và proxy `/api` |
| `backend` | 8000 | FastAPI, auth, workspace, LangGraph, calendar integration |
| `worker` | — | LMS projection và RAG ingestion |
| `lms-simulator` | 8010 | Canvas-compatible demo LMS |
| `pacewise-postgres` | 5433 | Workspace, session, memory, queue, checkpoint |
| `lms-postgres` | 5434 | Dữ liệu LMS demo |
| `qdrant` | 6333 | Vector store |
| `prometheus` | 9090 | Metrics, profile `observability` |
| `grafana` | 3001 | Dashboard, profile `observability` |

Các endpoint và lệnh chạy được ghi trong [README](../README.md). Kết quả kiểm chứng hiện tại nằm tại [evaluation-evidence.md](evaluation-evidence.md).
