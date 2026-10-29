# 5. Tài liệu kiểm thử

## Chiến lược

| Tầng | Nội dung |
|---|---|
| Unit | Domain services, scheduler, policies, reducers và UI utilities |
| API/integration | Auth, CSRF/RBAC, workspace, LMS sync, materials, assessment và sessions |
| Agent/evaluation | Routing, safety, RAG grounding, quality gate và deterministic scenarios |
| Frontend | Component behavior, accessibility, localization và state transitions |
| Database | Alembic migration trên PostgreSQL rỗng, xác minh schema/revision |
| Supply chain | `pip-audit`, `npm audit`, Docker image scan bằng Trivy |
| Performance | Locust và benchmark cho planning/replan/instructor views |

## Quality gate dùng trong CI

```text
Ruff
→ Backend tests + coverage >= 83%
→ Deterministic AI evaluation
→ Manual acceptance evidence (reproducible script)
→ LMS simulator tests
→ Frontend tests + typecheck + production build
→ Dependency audits
→ PostgreSQL migration smoke test
→ Backend/frontend Docker build + Trivy scan
```

Workflow nguồn: [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml).

## Lệnh tái hiện

```powershell
$env:APP_ENV='test'
$env:OPENAI_API_KEY='test-key'
$env:PYTHONUTF8='1'
python -m ruff check src/ evals/ tests/ lms-simulator/app/ lms-simulator/tests/
python -m pytest tests/ -q --cov=src --cov-report=term-missing --cov-fail-under=83
python -m evals.run_agent_eval
python -m evals.run_manual_evidence

Push-Location lms-simulator
python -m pytest tests/ -q
Pop-Location

Push-Location frontend/pacewise
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
Pop-Location
```

## Báo cáo và bằng chứng chi tiết

- [Evaluation evidence](../../evaluation-evidence.md)
- [Bộ thiết kế kiểm chứng bốn môn](../../testing/Bo_thiet_ke_kiem_chung_4_mon.docx)
- Test tự động và báo cáo máy đọc nằm trong `tests/`, `evals/` và CI; không lặp
  lại hàng loạt báo cáo theo ngày trong `docs`.

## Kết quả local gần nhất — 18/10/2026

| Gate | Kết quả |
|---|---:|
| Backend | **1.058 passed** |
| Backend coverage | **83,10%** (ngưỡng 83%) |
| Frontend unit/accessibility | **572 passed / 98 files** |
| Frontend TypeScript | **Passed** |
| Frontend production build | **Passed** |
| LMS simulator | **110 passed** |
| Deterministic AI evaluation | **Passed** |
| Reproducible acceptance evidence | **6/6 passed** |
| Ruff | **Passed** |
| Python / frontend dependency audit | **0 known vulnerabilities** |
| Backend / frontend production image build | **Passed** |
| Trivy HIGH/CRITICAL scan | **0 findings trên cả hai image** |

Các test mới của future planning xác minh cả bốn lớp: assignment tương lai vẫn
vào context của Plan, scheduler không xếp trước `earliest_start_at`, independent
quality gate từ chối `BEFORE_PREREQUISITE`, và API không cho mở Do trước mốc.

Kết quả chính xác của commit nộp bài phải lấy từ GitHub Actions của chính commit
đó; không dùng số test của commit cũ để đại diện cho bản phát hành mới.
