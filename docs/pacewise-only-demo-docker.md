# Chế độ cũ: một web PaceWise — LMS chạy nội bộ

> Đã thay thế ngày 10/10/2026: mặc định hiện tại chạy PaceWise độc lập, cả API
> và PostgreSQL simulator đã tắt. Xem [hướng dẫn standalone](pacewise-standalone-migration.md).
> Các lệnh bên dưới chỉ ghi lại kiến trúc cũ, không dùng để khởi động demo hiện tại.

Theo lựa chọn demo: chỉ mở web PaceWise, **vẫn giữ API LMS làm nguồn dữ liệu nội bộ**. Đây không phải chế độ tắt toàn bộ LMS. Đăng nhập, môn học, lịch, nhiệm vụ, trọng số và tài liệu vẫn sử dụng API simulator; không tạo thêm một nguồn dữ liệu khác.

## Tách trách nhiệm

| Bộ Docker | Thành phần | Truy cập |
|---|---|---|
| `docker-compose.yml`, project `pacewise` | Frontend, backend, worker, PostgreSQL PaceWise, Qdrant; observability tùy chọn | Web PaceWise ở cổng 5173 |
| `lms-simulator/docker-compose.yml`, project `pacewise-lms` | Backend/API simulator, PostgreSQL LMS, uploads; mã frontend cũ giữ trong `lms-simulator/static` | Không publish cổng; không phục vụ giao diện/static/Swagger |

Backend/worker kết nối `http://lms-api:8010` qua network `pacewise-lms-service`. Frontend không tham gia network này. PostgreSQL LMS chỉ nằm trên network database riêng. Các API vẫn kiểm tra service key, session và enrollment; việc giấu web không thay thế kiểm tra quyền.

Các nút quay lại LMS được ẩn ở cả hai role, desktop và mobile. PDF được đọc qua proxy PaceWise có xác thực. Liên kết tương đối tới web LMS cũ không còn hiển thị thành nút mở hỏng; link external hợp lệ vẫn được giữ.

## Chạy demo (từ thư mục gốc repo)

Trên máy mới, tạo volume một lần trước khi chạy (máy đang có dữ liệu không cần làm lại). Volume LMS là `external` để Compose không sở hữu/xóa nó khi dừng stack:

```powershell
docker volume create pacewise_lms_postgres_data
docker volume create pacewise_lms_uploads
```

Nếu cấu hình tên volume khác, tạo đúng hai tên đã chọn. Không trỏ một môi trường demo mới vào volume production đang hoạt động.

```powershell
docker compose --env-file .env -f lms-simulator/docker-compose.yml up -d --build --wait
docker compose up -d --build --wait
```

Mở `http://localhost:5173`. Dùng tài khoản PaceWise/demo hiện có, role tự nhận từ tài khoản. Không cần mở website LMS.

Hai project không có `depends_on` xuyên project. **Phải khởi động LMS API khỏe trước**, rồi PaceWise. Chỉ chạy stack PaceWise không có API nguồn sẽ không đủ cho đăng nhập/authoring/sync. Worker vẫn đồng bộ và gửi nhắc như trước.

```powershell
docker compose ps
docker compose --env-file .env -f lms-simulator/docker-compose.yml ps
```

## Dữ liệu và chuyển từ stack cũ

Volume cũ được giữ nguyên tên `pacewise_lms_postgres_data` và `pacewise_lms_uploads`; chuyển project không tạo database trắng. Có thể đổi tên đích qua `LMS_DATA_VOLUME`/`LMS_UPLOADS_VOLUME` nếu triển khai môi trường mới. Backup trước mọi di chuyển dữ liệu production.

Với máy đã chạy bản gộp, dừng và bỏ **hai container cũ**, không bỏ volume, trước khi chạy bộ mới:

```powershell
# Kiểm tra tên và volume trước. Đây là tên mặc định của bản gộp cũ.
docker inspect pacewise-lms-postgres-1 --format '{{range .Mounts}}{{.Name}} {{.Destination}}{{end}}'
docker stop pacewise-lms-simulator-1 pacewise-lms-postgres-1
docker rm pacewise-lms-simulator-1 pacewise-lms-postgres-1
```

Không chạy hai PostgreSQL cùng lúc trên cùng volume. Không dùng `down -v`, `volume prune` hoặc `system prune` cho thao tác này. Các tài khoản, lịch, nhiệm vụ và file không bị xóa. PaceWise database giữ nguyên project/volume.

## Khi muốn dùng lại web LMS

Mã giao diện, API, Dockerfile và dữ liệu vẫn ở `lms-simulator/`. Bật có chủ đích bằng override:

```powershell
docker compose --env-file .env -f lms-simulator/docker-compose.yml -f lms-simulator/docker-compose.web.yml up -d --build --wait
docker compose -f docker-compose.yml -f docker-compose.lms-web.yml up -d --build frontend
```

Web LMS local mở tại `http://localhost:8010`; nút chuyển LMS trong PaceWise được bật lại. Cổng chỉ bind loopback, không mở ra internet. Muốn quay về demo một web: chạy lại hai lệnh mặc định ở trên (frontend cần rebuild để đổi build-time flag).

## Dừng

```powershell
docker compose down
docker compose --env-file .env -f lms-simulator/docker-compose.yml down
```

`down` giữ dữ liệu nhưng tạm dừng dịch vụ; chỉ dừng LMS thì chức năng PaceWise phụ thuộc API cũng ngừng. Không dùng `--remove-orphans` khi quản lý nhiều bộ Compose nếu chưa đối chiếu container.

## Khi deploy AWS sau này

Chỉ công khai domain/reverse proxy HTTPS của PaceWise. Không mở security group cho 8010 hoặc database LMS. Stack đã tách được nhưng **chưa phải tuyên bố production-ready**: phải đổi toàn bộ mật khẩu/secret demo, cấu hình HTTPS/cookie/Google callback theo domain thật, giới hạn cổng backend/database/Qdrant và thêm backup. Các cổng local hiện có của PaceWise không nên được mở trực tiếp ra internet. Chưa thực hiện deploy cloud trong tác vụ này.
