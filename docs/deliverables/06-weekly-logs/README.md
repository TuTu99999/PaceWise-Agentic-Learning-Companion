# 6. Nhật ký tuần

Nhật ký dưới đây được tổng hợp từ Git history và pull requests đến ngày
18/10/2026. Nó ghi nhận đầu ra kỹ thuật có thể truy vết; không tự suy đoán người
thực hiện hoặc số giờ khi commit không cung cấp thông tin đó.

## Tuần 1 — 27/09 đến 03/10/2026

- Tích hợp frontend PaceWise và LMS simulator.
- Hoàn thiện nền tảng agent, RAG, observability và deterministic evaluation.
- Tích hợp Google Calendar/ICS và hợp nhất dependency stack.
- Làm giàu dữ liệu LMS cho planner; tăng safety cho planning/RAG.
- Hoàn thiện các workflow học tập, recovery và giao diện Plan/Do.
- Bổ sung CI ổn định cho Python/frontend trên self-hosted runner.

## Tuần 2 — 04/10 đến 10/10/2026

- Hoàn thiện workflow demo Plan → Do → Reflect.
- Bổ sung học liệu cho DSA, Database và OOP.
- Tích hợp chatbot, course materials và nhiều vòng UX/evaluation.
- Kiểm tra calendar, reflection, responsive UI, teacher overview, RAG/material
  sync, security, SSO và observability.

## Tuần 3 — 11/10 đến 17/10/2026

- Ổn định CI/CD, migration PostgreSQL và dependency lock.
- Xây dựng pipeline AWS ECR → EC2 qua OIDC/SSM và HTTPS bằng Caddy.
- Sửa Docker credential/ECR immutable image handling trên Windows runner.
- Hoàn thiện production health checks và rollback.
- Cải thiện instructor dashboard, roster, tài liệu/chapter selection.
- Bổ sung assignment content analysis, plan confirmation và Reflect sau Do.
- Tối ưu instructor views, xóa tài nguyên an toàn và UI song ngữ.
- Xây dựng rubric-based understanding check và adaptive assessment flow.

## Tuần 4 — 18/10/2026

- Hoàn thiện luồng assessment có cấu trúc phục vụ Plan/Replan.
- Cho phép phản tư tuần cập nhật liên tục và giữ bản hiện hành mới nhất.
- Chuẩn hóa future planning: assignment vẫn xuất hiện trước buổi học, nhưng Do
  chỉ được xếp/mở từ `earliest_start_at`.
- Chuẩn hóa bộ hồ sơ bàn giao trong `docs/deliverables`.

## Nguồn đối chiếu

- `git log --date=short --oneline`
- Pull requests và CI tại repository GitHub.
- [Evaluation evidence](../../evaluation-evidence.md)

Hai template cũ ở [`JOURNAL.md`](../../../JOURNAL.md) và
[`WORKLOG.md`](../../../WORKLOG.md) vẫn có thể dùng nếu team cần bổ sung tên
thành viên, thời lượng và ghi chú quản trị không có trong Git.
