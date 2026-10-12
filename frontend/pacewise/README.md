# PaceWise — Frontend

React + Vite + TypeScript + React Router + Tailwind CSS. Giao diện dùng PaceWise FastAPI cho đăng nhập, LMS sync, workspace, instructor actions và LangGraph agent; dữ liệu mẫu trong `src/data` chỉ phục vụ trạng thái demo/fallback.

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
```

Từ thư mục gốc repo, có thể chạy toàn bộ frontend, backend, LMS simulator và hai PostgreSQL bằng:

```bash
docker compose up -d --build
```

Container frontend dùng Nginx phục vụ bản build và reverse proxy `/api` sang backend, nên browser không cần biết địa chỉ nội bộ của backend hoặc service key của LMS.

Tài khoản demo (mật khẩu `demo123`):
- `sinhvienmoi@pacewise.edu`: sinh viên mới, chưa có kế hoạch → Dashboard trống → Tạo kế hoạch
- `sinhvien@pacewise.edu`: sinh viên đã có lịch tuần
- `giangvien@pacewise.edu`: giảng viên (Tổng quan lớp, Review Queue, Assessment → Sửa câu hỏi & rubric)
- `khach@pacewise.edu`: tài khoản không có quyền → trang 403 (sinh viên mở link giảng viên cũng ra 403)

## Cấu trúc
- `src/components/ui` — Button, Card, Field (Input/Select/Textarea), Modal, Badge, ProgressBar, Stepper, States (Empty/Loading/Error/Banner), Toast
- `src/components/domain` — TaskCard, NextActionCard, Schedule, WarningCard, Citation/SourceModal, DiffList, EditBlockModal, StatTile
- `src/pages` — student / instructor / auth
- `src/layouts` — AppShell (sidebar desktop, bottom nav mobile), StudentLayout, InstructorLayout
- `src/routes` — AppRoutes, guards (RequireRole)
- `src/store` — AppStore (Context + useReducer, lưu localStorage)
- `src/services/api.ts` — client HTTP tới FastAPI, gửi cookie PaceWise và CSRF; Plan, QA và Hint gọi `/api/v1/chat`
- `src/utils` — scheduler (xếp lịch + tính khả thi), progress (drift, việc tiếp theo), recovery (phương án + diff), qa (guardrail + trả lời có nguồn)
- `src/data` — mock data

Ngày demo cố định: Thứ Ba 29/09/2026 09:00 (GMT+7) — xem `src/utils/time.ts`.
Cài đặt → Công cụ demo: mô phỏng lỗi AI, dữ liệu Canvas cũ, trạng thái chưa có kế hoạch.

`tools/` chỉ dùng cho môi trường build không có npm registry (esbuild + shim router); không cần khi chạy bằng Vite.
