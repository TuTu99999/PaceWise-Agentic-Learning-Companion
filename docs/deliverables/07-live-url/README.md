# 7. Live URL

## Production

> **Live URL:** <https://c4-app-008.io.vn/>

## Tài khoản demo production

| Vai trò | Email | Cách đăng nhập |
|---|---|---|
| Sinh viên | `canhquat213@gmail.com` | Chọn **Tiếp tục với Google** |
| Giảng viên | `teacher1@pacewise.edu.vn` | Mật khẩu demo cung cấp riêng cho mentor |

Trước khi nộp, mở URL bằng cửa sổ ẩn danh và xác minh:

- landing/login tải qua HTTPS;
- đăng nhập được bằng tài khoản demo hợp lệ;
- Plan, Do, Self-check và Reflect hoạt động;
- `/health` và `/api/v1/status` trả trạng thái khỏe;
- browser không gọi trực tiếp database, LMS internal port hoặc secret endpoint;
- Không đưa mật khẩu, token, API key hoặc khóa bí mật vào URL, video hay slide.

## Local demo

- PaceWise: <http://localhost:5173>
- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

Hướng dẫn chạy: [`../../../README.md`](../../../README.md). Hướng dẫn production:
[`../../production-configuration.md`](../../production-configuration.md).
