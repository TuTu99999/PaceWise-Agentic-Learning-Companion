# Đặc tả Tính năng: Giao diện Hỏi đáp RAG phong cách Google Gemini (Light Theme)

## 1. Mục tiêu
Nâng cấp giao diện Học tập & Hỏi đáp (`/learn`) của người học theo ngôn ngữ thiết kế của Google Gemini Web:
- **Tông màu sáng thanh lịch (Light mode)**: Sử dụng nền xám bạc nhẹ `#F0F4F9` / `#F8FAFC`, bề mặt trắng tinh `#FFFFFF` với độ tương phản cao, tối ưu công thái học khi đọc tài liệu.
- **Sidebar quản lý đa phiên trò chuyện (Multi-session Chat History)**:
  - Nút `+ Cuộc trò chuyện mới` tạo phiên hội thoại mới.
  - Ô tìm kiếm đoạn chat theo từ khóa trong tiêu đề và nội dung tin nhắn.
  - Danh sách phân nhóm theo thời gian (Hôm nay, 7 ngày trước, Cũ hơn).
  - Thao tác nhanh khi hover: Sửa tiêu đề (Rename/Edit) và Xóa (Delete) đoạn chat.
- **Không gian trò chuyện chính (Gemini Main Canvas)**:
  - Hero greeting với icon Sparkle AI lấp lánh khi bắt đầu phiên mới.
  - Các thẻ gợi ý câu hỏi (Prompt chips) bo góc mềm mại.
  - Tin nhắn câu hỏi người học căn phải; phản hồi AI căn trái kèm trích dẫn tài liệu học liệu Qdrant (`[Tên tài liệu, Trang X, Đoạn Y]`).
  - Thanh nhập lệnh đáy trang dạng viên thuốc nổi (`Floating Pill Prompt Bar`) với nút gửi tròn màu xanh.
- **Lưu trữ dữ liệu bền vững (Persistence)**:
  - Lưu cấu trúc `qaConversations` vào PostgreSQL `UserWorkspace` qua API `/workspace` và `localStorage` cục bộ.

## 2. Contracts & Data Models
```typescript
export interface QAConversation {
  id: string;
  courseId: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: QAMessage[];
}
```

## 3. Quyết định Kỹ thuật
- Tương thích ngược: Tự động di chuyển `qaMessages` cũ thành cuộc trò chuyện đầu tiên nếu chưa có conversation nào.
- Tự động đặt tiêu đề theo câu hỏi đầu tiên của người học (tối đa 40 ký tự).
- Đồng bộ mượt mà vào `AppStore` và `WORKSPACE_KEYS` của backend (`qaConversations`, `activeConversationId`).
