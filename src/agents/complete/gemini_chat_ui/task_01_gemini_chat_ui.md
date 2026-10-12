# Task 01: Xây dựng Giao diện Hỏi đáp RAG phong cách Google Gemini (ĐÃ HOÀN THÀNH)

## 1. Scope đã thực hiện
- Mở rộng types: Thêm `QAConversation` vào [types/index.ts](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/frontend/pacewise/src/types/index.ts).
- Cập nhật backend: Thêm `qaConversations`, `activeConversationId` vào `WORKSPACE_KEYS` trong [src/api/workspace.py](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/src/api/workspace.py).
- Mở rộng AppStore: Thêm các actions `CREATE_QA_CONVERSATION`, `SELECT_QA_CONVERSATION`, `RENAME_QA_CONVERSATION`, `DELETE_QA_CONVERSATION`, cơ chế debounce lưu vào PostgreSQL và cache vào `localStorage` trong [AppStore.tsx](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/frontend/pacewise/src/store/AppStore.tsx).
- Xây dựng giao diện Google Gemini hoàn chỉnh trên [LearnPage.tsx](file:///f:/VinUniversity/Multiagent_LMS_Canvas/P-008/frontend/pacewise/src/pages/student/LearnPage.tsx):
  - Sidebar bên trái: Nút `+ Cuộc trò chuyện mới`, thanh tìm kiếm realtime, danh sách phân nhóm (Hôm nay, 7 ngày trước, Cũ hơn), các nút Sửa tên và Xóa.
  - Main Canvas: Tông màu sáng thanh lịch (`#F0F4F9`), biểu tượng ngôi sao Sparkle AI, tiêu đề chào đón, 3 thẻ gợi ý thông minh, và thanh nhập lệnh Floating Pill Prompt Bar bo tròn 28px ở đáy.

## 2. Bằng chứng nghiệm thu (Acceptance Evidence)
1. **Frontend TypeScript & Vite Production Build**:
   ```
   > pacewise@1.0.0 build
   > tsc -b && vite build
   ✓ 104 modules transformed.
   dist/assets/LearnPage-C7XSQKgQ.js 27.45 kB
   ✓ built in 3.05s
   ```
2. **Docker Deployment**:
   - `pacewise-frontend-1`: Recreated & Started healthy.
   - `pacewise-backend-1`: Updated `workspace.py` with `qaConversations` & `activeConversationId` in `WORKSPACE_KEYS`.
   - `pacewise-postgres-1`: Bảng `pacewise_workspaces` lưu trữ trạng thái đa phiên chat bền vững.
