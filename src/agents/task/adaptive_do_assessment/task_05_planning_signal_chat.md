# Task 05 — Planning-signal chatbot

## Mục tiêu

Thu gọn checkpoint trong Do thành luồng hỏi → ghi nhận structured planning signal → hỏi tiếp/kết thúc. Giảng viên chỉ duyệt thiết kế câu hỏi và rubric, không duyệt từng câu trả lời sinh viên.

## Scope và contract

- Adaptive Understanding yêu cầu model trả JSON thuần; không sinh báo cáo Markdown cho sinh viên.
- Evidence/rubric/confidence tiếp tục được lưu ở backend để Plan/Replan đọc có kiểm soát.
- Evidence chưa chắc chắn được kiểm chứng tối đa theo server limit; hết giới hạn thì `abstained`/unknown và không tạo `AgentReviewCase`.
- UI chỉ hiện câu hỏi, câu trả lời, gợi ý, một xác nhận ngắn cho Plan và câu/hành động tiếp theo.
- Locale English/Vietnamese phải áp dụng cho toàn bộ copy do checkpoint tự sinh.
- Assessment không tự sửa lịch và không tạo điểm môn học.
- Planning metric gồm outcome, confidence, tested/passed/failed dimensions, criterion pass/fail, hint level và support condition.
- Failure đã xác nhận ở bất kỳ stage Recall → Transfer đều tạo mastery risk/re-plan draft có giới hạn; unknown/abstained không tác động Plan.
- Có ngân hàng đủ năm stage cho DB201, DSA201, OOPCPP201 và WEB201; câu mới ở trạng thái chờ giảng viên duyệt.

## Edge cases

- Reload ở trạng thái verification/stopped/completed vẫn chỉ hiện trạng thái ngắn.
- Kết quả legacy `review_required` không làm lộ copy “chờ giảng viên”.
- Malformed output không được ghi thành năng lực yếu hoặc tạo snapshot kiến thức.
- Unconfirmed evidence không được kích hoạt replan hoặc Knowledge State update.

## File dự kiến

- `src/agents/prompts/understanding.py`
- `src/agents/workflows/understanding.py`
- `src/api/adaptive_assessment.py`
- `src/services/assessment_review_policy.py`
- `src/services/learning_evidence.py`
- `frontend/pacewise/src/components/domain/AdaptiveDoCheckpoint.tsx`
- test backend/frontend liên quan

## Nghiệm thu

- Test frontend checkpoint pass và không render raw feedback/rubric/confidence.
- Test review policy + adaptive API pass; không có review case từ answer flow.
- Full frontend test/build và backend suite liên quan pass.
- Docker local được rebuild và health check đạt.

## Bằng chứng hiện tại

- Backend: `1039 passed`, coverage `83.22%`.
- Frontend: `98` test files, `569 passed`; typecheck và production build thành công.
- Focused assessment/Plan tests: `68 passed`; bao gồm unknown không đổi Plan và failure ở Recall/Transfer tạo risk nhưng không auto-apply.
- Local PostgreSQL: tạo Q-67–Q-82, 16/16 câu mới chờ duyệt cho 4 môn; seed chạy lại cho `24 unchanged`, không trùng.
- Local health hiện có: API `8000/health` trả 200, frontend `5173` trả 200.
- Migration chạy thành công trên PostgreSQL 16 sạch; backend/frontend image build thành công và Trivy không phát hiện lỗ hổng HIGH/CRITICAL có bản vá.
