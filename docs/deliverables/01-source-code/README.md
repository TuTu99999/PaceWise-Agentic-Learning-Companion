# 1. Source code

Mã nguồn đầy đủ của PaceWise là toàn bộ repository:

- Repository: <https://github.com/AI20K-Build-Phase-Cohort-4/P-008>
- Nhánh phát hành chính: `main`
- README chạy dự án: [`../../../README.md`](../../../README.md)

## Thành phần

| Thư mục/tệp | Nội dung |
|---|---|
| `src/` | FastAPI backend, agent workflows và domain services |
| `frontend/pacewise/` | React + TypeScript frontend |
| `lms-simulator/` | Canvas-compatible LMS simulator và contract tests |
| `alembic/` | Database migrations |
| `tests/` | Backend, API, agent và evaluation tests |
| `evals/` | Deterministic AI evaluation và acceptance evidence |
| `load_tests/` | Kịch bản tải bằng Locust |
| `deploy/` | AWS EC2/ECR/SSM deployment assets |
| `.github/workflows/` | CI và CD workflows |
| `docs/` | Tài liệu dự án và bộ hồ sơ này |

## Cách tạo bản nộp source

Khuyến nghị nộp URL repository kèm commit SHA của bản demo. Nếu cần file nén,
tạo GitHub source archive từ đúng tag/commit; không nén `node_modules`, virtual
environment, `.env`, database local hoặc cache Docker.
