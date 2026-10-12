# PaceWise — Sitemap và Information Architecture

**Phiên bản:** 1.0  
**Nguyên tắc:** điều hướng theo nhiệm vụ người dùng, không theo tên agent nội bộ

## 1. Sitemap tổng thể

```text
PaceWise
├── Đăng nhập / chọn vai trò
├── Student Experience
│   ├── Tổng quan tuần
│   │   ├── Việc tiếp theo
│   │   ├── Tiến độ và quỹ thời gian
│   │   ├── Deadline quan trọng
│   │   └── Tín hiệu nguy cơ
│   ├── Kế hoạch
│   │   ├── Mục tiêu và assignment
│   │   ├── Quỹ thời gian
│   │   ├── Đang tạo kế hoạch
│   │   ├── Bản xem trước
│   │   └── Kế hoạch đã xác nhận
│   ├── Học tập
│   │   ├── Hỏi tài liệu
│   │   │   ├── Câu trả lời có nguồn
│   │   │   ├── Không đủ nguồn
│   │   │   └── Báo citation sai
│   │   └── Kiểm tra mức hiểu
│   │       ├── Chọn đơn vị kiến thức
│   │       ├── Làm 1–3 câu
│   │       └── Kết quả và hành động tiếp
│   ├── Tiến độ
│   │   ├── Phiên học
│   │   ├── Lịch sử thực tế
│   │   └── Cảnh báo nguy cơ
│   ├── Phục hồi kế hoạch
│   │   ├── Các phương án
│   │   ├── So sánh đánh đổi
│   │   ├── Diff trước–sau
│   │   └── Xác nhận
│   ├── Tổng kết tuần
│   │   ├── Dữ kiện tuần
│   │   ├── Ba câu phản tư
│   │   └── Điều chỉnh tuần sau
│   └── Cài đặt
│       ├── Môn pilot và nguồn dữ liệu
│       ├── Thời gian rảnh mặc định
│       ├── Mức ưu tiên
│       ├── Quyền riêng tư
│       └── Khả năng tiếp cận
└── Management Console
    ├── Tổng quan lớp
    │   ├── Tiến độ tổng hợp
    │   ├── Xu hướng nguy cơ
    │   └── Bằng chứng theo đơn vị kiến thức
    ├── Nội dung đánh giá
    │   ├── Mục tiêu
    │   ├── Câu hỏi/đáp án
    │   └── Rubric
    ├── Hàng chờ
    │   ├── Độ tin cậy thấp
    │   ├── Citation bị phản ánh
    │   └── Tín hiệu cần hỗ trợ
    └── Xác nhận hỗ trợ
        ├── Căn cứ
        ├── Nội dung xem trước
        └── Audit quyết định
```

## 2. Điều hướng Student Experience

Thanh điều hướng chính đề xuất:

| Nhãn | Đích | Lý do |
|---|---|---|
| Tổng quan | Dashboard tuần | Điểm vào thường xuyên nhất |
| Kế hoạch | Plan và lịch đã xác nhận | Tập trung tạo/chỉnh lịch |
| Học tập | Q&A và Check | Gộp hai nhu cầu học nội dung |
| Tiến độ | Phiên học và cảnh báo | Theo dõi thực tế |
| Tổng kết | Reflect | Hoạt động theo tuần |

Recover không cần là mục điều hướng chính; nó xuất hiện theo ngữ cảnh từ cảnh báo hoặc nút “Điều chỉnh kế hoạch”.

Trên mobile dùng bottom navigation tối đa năm mục. Cài đặt đặt trong menu tài khoản.

## 3. Điều hướng Management Console

| Nhãn | Đích |
|---|---|
| Tổng quan lớp | Dữ liệu tổng hợp `n ≥ 5` |
| Nội dung | Mục tiêu, câu hỏi, rubric |
| Hàng chờ | Ca cần con người xem |
| Audit | Lịch sử phê duyệt và hỗ trợ |

Student Experience và Management Console phải tách theo RBAC; không chỉ ẩn menu ở client.

## 4. Quy tắc đặt tên

- Dùng từ người dùng hiểu: “Kế hoạch”, “Hỏi tài liệu”, “Kiểm tra mức hiểu”.
- Không hiển thị tên kỹ thuật như `Coordinator`, `RAG`, `node`, `state` trong UI chính.
- “Recover” được hiển thị là “Phục hồi kế hoạch” hoặc “Điều chỉnh khi bị trễ”.
- “Reflect” được hiển thị là “Tổng kết tuần”.
- “Assessment” được hiển thị là “Bằng chứng hiểu bài”, không gọi là “điểm”.

## 5. Breadcrumb và deep link

- Desktop dùng breadcrumb từ cấp hai trở xuống, ví dụ `Kế hoạch / Bản xem trước`.
- Citation có deep link tới đúng tài liệu/đoạn và mở trong side panel hoặc tab mới.
- Cảnh báo deep link tới đúng assignment và phương án Recover liên quan.
- Khi quay lại từ citation hoặc modal, giữ nguyên nội dung người dùng đang nhập.
- URL không chứa nội dung học tập thô hoặc thông tin nhạy cảm.

## 6. Quy tắc trạng thái điều hướng

- Badge cảnh báo chỉ hiển thị số lượng có thể hành động.
- “Bản xem trước” không được đánh dấu như kế hoạch đã lưu.
- Nếu dữ liệu Canvas cũ, banner xuất hiện trên mọi màn hình phụ thuộc dữ liệu đó.
- Khi có tác vụ đang xử lý, người dùng vẫn có thể rời màn hình; trạng thái được khôi phục khi quay lại.
- Route sai quyền chuyển đến trang 403 có đường quay về bề mặt đúng vai trò.

