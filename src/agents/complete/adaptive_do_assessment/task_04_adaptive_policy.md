# Task 04 — Adaptive policy và evidence gates (hoàn thành engineering)

## Đầu ra

- Checkpoint Recall → Explain → Why → Application → Transfer dùng câu hỏi, KC và rubric do server tải từ bản giảng viên duyệt.
- Câu trả lời được chấm theo từng tiêu chí 0–4, kèm trích dẫn nguyên văn; không cộng thành điểm môn học.
- Self-report, câu dài, metadata hoặc câu dùng hint không tự nâng Knowledge State.
- Kết quả không chắc chắn được hỏi kiểm chứng có giới hạn rồi mới chuyển hàng chờ giảng viên; không khóa học, Reflect hay Plan.
- Delayed probe kiểm tra retention tách khỏi biểu hiện tức thời.
- UI hiển thị trạng thái mức hiểu, tên tiêu chí, nhãn chẩn đoán và bằng chứng thay vì chỉ hiện mã/điểm số.
- Ngôn ngữ phản hồi Assessment Agent đi theo lựa chọn Việt/Anh của giao diện.

## Bằng chứng nghiệm thu

- Offline adaptive: 60/60 engineering boundary cases pass.
- Live model `cx/gpt-5.6-sol` ngày 2026-10-17: 8/8 ca khớp nhãn, 0 false-pass, 0 abstention.
- Backend: 1019/1019 tests pass; targeted assessment/calibration/locale 73/73 pass.
- Frontend: 544/544 tests pass; TypeScript typecheck và production build pass.
- Báo cáo: `evals/reports/adaptive-assessment-live-2026-10-17-v2.json`.

## Giới hạn

Live set chỉ gồm 8 ca toán do developer gán nhãn. Kết quả này xác nhận kết nối và các gate kỹ thuật, không chứng minh
AI đo đúng mức hiểu của sinh viên trong thực tế. Trước production vẫn cần SME labels, calibration và pilot người học.
