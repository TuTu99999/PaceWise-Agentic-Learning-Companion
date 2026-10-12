# Kế hoạch Thực hiện: Giao diện Hỏi đáp RAG phong cách Google Gemini

## 1. Thứ tự & Phụ thuộc
1. **Giai đoạn 1**: Mở rộng Data Models & AppStore:
   - Thêm `QAConversation` vào `frontend/pacewise/src/types/index.ts`.
   - Cập nhật `AppStore.tsx` hỗ trợ `qaConversations`, `activeConversationId`, các actions: `CREATE_QA_CONVERSATION`, `SELECT_QA_CONVERSATION`, `RENAME_QA_CONVERSATION`, `DELETE_QA_CONVERSATION`, `ADD_QA` (ghi vào conversation hiện tại).
   - Thêm `qaConversations`, `activeConversationId` vào `WORKSPACE_KEYS` trong `src/api/workspace.py`.
2. **Giai đoạn 2**: Thiết kế Component Sidebar Lịch sử Hội thoại phong cách Gemini:
   - Nút `+ Cuộc trò chuyện mới`
   - Ô tìm kiếm đoạn chat (lọc realtime)
   - Danh sách session có inline rename và nút delete
   - Nút thu gọn/mở rộng sidebar linh hoạt
3. **Giai đoạn 3**: Tái cấu trúc khu vực Main Chat Canvas trên `LearnPage.tsx`:
   - Hero greeting với icon Sparkle Gemini, thẻ gợi ý câu hỏi bo tròn.
   - Luồng chat với bong bóng câu hỏi (User bubble) và phản hồi AI (Assistant bubble) đính kèm trích dẫn RAG.
   - Floating Pill Prompt Bar ở đáy bo tròn 28px với nút gửi hình tròn.
4. **Giai đoạn 4**: Build, Deploy Docker container và nghiệm thu giao diện.

## 2. Mốc nghiệm thu (Acceptance Criteria)
- [ ] Giao diện tông màu sáng đúng theo ảnh mockup Gemini.
- [ ] Tạo được cuộc trò chuyện mới (+ Cuộc trò chuyện mới).
- [ ] Tìm kiếm được các đoạn chat cũ qua ô tìm kiếm.
- [ ] Đổi được tên/tiêu đề cuộc trò chuyện.
- [ ] Xóa được cuộc trò chuyện khỏi danh sách và CSDL.
- [ ] Reload trang hoặc chuyển qua lại giữa các môn học không bị mất dữ liệu chat.
