# PaceWise — User Flows

**Phiên bản:** 1.0  
**Quy ước:** mọi hành động ghi dữ liệu quan trọng đều có preview và confirmation

## 1. Luồng khởi tạo

```mermaid
flowchart TD
    A[Đăng nhập] --> B{Xác định vai trò}
    B -->|Sinh viên| C{Có dữ liệu tuần?}
    B -->|Giảng viên| D{Đủ dữ liệu tổng hợp?}
    B -->|Sai quyền| E[Thông báo 403 và đường quay lại]
    C -->|Không| F[Empty state: dùng fixture hoặc đồng bộ]
    C -->|Có| G[Tổng quan tuần]
    D -->|Không hoặc n < 5| H[Ẩn dashboard và giải thích ngưỡng]
    D -->|Có| I[Tổng quan lớp]
```

## 2. Plan — tạo kế hoạch tuần

```mermaid
flowchart TD
    A[Tổng quan hoặc empty state] --> B[Chọn tuần và assignment]
    B --> C[Nhập mục tiêu, ưu tiên, availability]
    C --> D{Dữ liệu hợp lệ?}
    D -->|Không| E[Đánh dấu trường lỗi và hướng dẫn sửa]
    E --> C
    D -->|Có| F[Đang phân rã và kiểm tra lịch]
    F --> G{Timeout/lỗi?}
    G -->|Có| H[Giữ dữ liệu; thử lại hoặc dùng mẫu cơ bản]
    H --> F
    G -->|Không| I{Có lịch khả thi?}
    I -->|Không| J[Hiện số giờ thiếu, xung đột và lựa chọn]
    J --> C
    I -->|Có| K[Bản xem trước — chưa lưu]
    K --> L{Quyết định}
    L -->|Sửa| C
    L -->|Hủy| M[Giữ kế hoạch cũ]
    L -->|Xác nhận| N[Lưu và ghi audit]
    N --> O[Tổng quan với kế hoạch mới]
```

### Điều kiện hoàn thành

- Người dùng thấy tổng thời lượng, deadline, phụ thuộc, giả định và xung đột.
- Không lưu trước khi bấm “Xác nhận và lưu”.
- Trường hợp vô nghiệm không có nút xác nhận kế hoạch.

## 3. Do/Tracking — cập nhật tiến độ

```mermaid
flowchart TD
    A[Tổng quan tuần] --> B[Chọn việc tiếp theo]
    B --> C{Cách ghi nhận}
    C -->|Bắt đầu phiên| D[Timer]
    C -->|Nhập thủ công| E[Form thời gian thực tế]
    D --> F[Kết thúc phiên]
    E --> G[Xác nhận dữ liệu]
    F --> G
    G --> H[Tính sai lệch và slack]
    H --> I{Có nguy cơ?}
    I -->|Không| J[Cập nhật dashboard]
    I -->|Có| K[Cảnh báo: dữ kiện → ảnh hưởng → lựa chọn]
    K --> L{Người dùng chọn}
    L -->|Dữ liệu sai| E
    L -->|Tiếp tục| J
    L -->|Phục hồi| M[Recover]
```

## 4. Q&A — hỏi đáp có nguồn

```mermaid
flowchart TD
    A[Nhập câu hỏi] --> B[Kiểm tra an toàn và ý định]
    B --> C{Yêu cầu làm hộ?}
    C -->|Có| D[Giải thích ranh giới]
    D --> E[Gợi ý khái niệm, ví dụ tương tự, yêu cầu cách làm thử]
    C -->|Không| F[Tìm học liệu]
    F --> G{Nguồn đủ?}
    G -->|Không| H[Nêu phần chưa xác minh và tài liệu cần xem]
    G -->|Có| I[Trả lời kèm citation]
    I --> J{Citation có vấn đề?}
    J -->|Có| K[Ghi nhận phản ánh và tạm loại khỏi căn cứ]
    J -->|Không| L[Câu hỏi tiếp theo]
    K --> L
    H --> L
    E --> L
```

## 5. Check — kiểm tra mức hiểu

```mermaid
flowchart TD
    A[Chọn đơn vị kiến thức] --> B[Hiện mục tiêu và 1–3 câu]
    B --> C[Nhập/nộp câu trả lời]
    C --> D[Đang đánh giá]
    D --> E{Đủ bằng chứng và tin cậy?}
    E -->|Không| F[Chưa đủ bằng chứng + lý do]
    F --> G[Gửi hàng chờ hoặc làm thêm câu]
    E -->|Có| H[Hiện một trong bốn trạng thái]
    H --> I[Phân tích 4 khía cạnh + evidence]
    I --> J[Chọn một hành động tiếp theo]
    J --> K[Thêm vào kế hoạch hoặc tiếp tục học]
```

## 6. Recover — phục hồi kế hoạch

```mermaid
flowchart TD
    A[Cảnh báo hoặc yêu cầu chủ động] --> B[Chụp snapshot kế hoạch]
    B --> C[Tạo và validate candidate schedules]
    C --> D{Có nghiệm khả thi?}
    D -->|Không| E[Nêu giờ thiếu và gợi ý trao đổi]
    D -->|Có| F[So sánh 2–3 phương án]
    F --> G[Chọn phương án]
    G --> H[Diff trước–sau]
    H --> I{Xác nhận?}
    I -->|Không| J[Giữ kế hoạch cũ]
    I -->|Sửa| C
    I -->|Có| K[Cập nhật lịch và ghi audit]
    K --> L[Thông báo kế hoạch mới đã áp dụng]
```

### Tiêu chí so sánh cố định

1. Việc giữ lại.
2. Việc dời hoặc giảm phạm vi.
3. Thời gian thiếu/dư.
4. Deadline được bảo vệ.
5. Rủi ro còn lại.

## 7. Reflect — tổng kết tuần

```mermaid
flowchart TD
    A[Cuối tuần hoặc người dùng mở] --> B[Xem dữ kiện kế hoạch–thực tế]
    B --> C[Trả lời tối đa ba câu]
    C --> D[AI tạo bản tóm tắt trung lập]
    D --> E[Đề xuất đúng một điều chỉnh]
    E --> F{Người dùng chọn}
    F -->|Chỉ lưu phản tư| G[Không đổi tuần sau]
    F -->|Sửa| H[Chỉnh điều chỉnh]
    H --> E
    F -->|Xác nhận| I[Lưu effective_week = tuần sau]
```

## 8. Giảng viên/cố vấn

```mermaid
flowchart TD
    A[Tổng quan lớp n ≥ 5] --> B{Mục tiêu}
    B -->|Xu hướng| C[Xem tiến độ và đơn vị kiến thức]
    B -->|Duyệt nội dung| D[Xem mục tiêu, câu hỏi, rubric]
    B -->|Xử lý ca| E[Hàng chờ]
    D --> F{Duyệt?}
    F -->|Không| G[Trả lại kèm ghi chú]
    F -->|Có| H[Xuất bản cho pilot]
    E --> I[Xem evidence, confidence, giới hạn]
    I --> J{Hỗ trợ cá nhân?}
    J -->|Không| K[Ghi chú tổng hợp]
    J -->|Có| L[Xem trước đối tượng và nội dung]
    L --> M[Xác nhận và audit]
```

## 9. Luồng lỗi chung

```mermaid
flowchart TD
    A[Tác vụ thất bại] --> B[Hiện thông điệp, request ID, trạng thái dữ liệu]
    B --> C{Có fallback an toàn?}
    C -->|Có| D[Thử lại hoặc dùng chức năng không AI]
    C -->|Không| E[Giữ input và hướng dẫn bước tiếp]
    D --> F{Người dùng thử lại?}
    F -->|Có| G[Idempotency key ngăn ghi trùng]
    F -->|Không| H[Quay về trạng thái an toàn]
```

