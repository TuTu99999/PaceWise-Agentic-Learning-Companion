# Adaptive Do Assessment

## Mục tiêu

Hoàn thiện Phase 2 của PaceWise: Do Agent điều phối phiên học, hỗ trợ RAG/chat và gọi
Adaptive Assessment như một sub-agent để tạo learning evidence có thể audit. Knowledge
State là derived state theo KC; Reflect chỉ tạo planning signal và không tự sửa lịch.

## Phạm vi thực thi 2026-10-08

- Session được lưu ở server, scoped institution/student/course/block/KC, không phụ thuộc tuần đăng nhập.
- Recall → Explain → Why → Application → Transfer. Không đủ item được duyệt: `coverage_gap`, không tự skip.
- Mỗi stage chỉ nhận dimension đã kiểm tra; stage trước được cộng dồn từ evidence chấp nhận của chính session.
- Item ID mới nhưng cùng text không được coi là bài biến thể chưa thấy.
- Hint H1–H5 lấy từ nội dung được duyệt hoặc lời hướng dẫn quy trình. Hint cao không tự sinh lời giải.
- Open rubric: criterion diagnostic 0–4 có anchors và quotes; không cộng điểm tổng/gradebook/probability.
- Delayed probe mặc định sau 48h, cấu hình 24–720h. Không phải thời gian đã calibrate với sinh viên.
- Retention cần baseline đúng user/course/KC, probe tới hạn, item chưa dùng và không hint. Lưu `retained_level` để không biến retention của application thành transfer.
- Metadata/level của item, self-report hay quote bịa không được nâng Knowledge State.
- Evidence hợp lệ bị failed được lưu như observation với unresolved_dimensions. Giữ level đã chứng minh lịch sử nhưng Plan thấy lỗ hổng mới; `no_evidence` không có observation thất bại vẫn là unknown, không mặc định yếu.
- Misconception: hypothesis có quote → retrieve taxonomy duyệt → lexical rerank → suspected/unknown. Đây chỉ là planning signal; không tạo việc duyệt từng câu trả lời cho giảng viên.
- Reflect không chấm lại kiến thức. Re-plan policy giữ lịch khi tín hiệu nhỏ/duplicate/cooldown, đề xuất draft cho drift đủ lớn; diff và confirm vẫn bắt buộc.
- Preserve history/ongoing blocks; không lấy assessment của một block/môn khác làm evidence cho phản tư hoạt động.
- Giữ API understanding/checkpoint cũ cho compatibility. UI Do mới dùng server-owned adaptive endpoint.

## Contract

### Do checkpoint input

- Assessment phải được giảng viên duyệt và tải từ server; client không được gửi đáp án chuẩn/rubric.
- Bắt buộc có `assessment_id`, `block_id`, câu trả lời và event key; API adaptive tự giữ `first_attempt`, `hint_level` (H0-H5), không tin số client gửi.
- `knowledge_component_ids` lấy từ metadata đã duyệt; thiếu mapping phải dùng `unmapped:<assessment_id>` và đánh dấu provisional.

### Learning evidence

- Append-only, idempotent theo `event_key`; schema/evaluator/rubric đều có version.
- Ghi response, item type, first-attempt, hint level, evidence quotes, dimensions, source refs và provenance.
- Sinh metric Plan có cấu trúc: outcome, confidence, các dimension đã test/đạt/chưa đạt, số criterion đạt/chưa đạt, mức hint và support condition.
- Chỉ evidence `accepted`, medium/high confidence, không provisional mới được tạo unresolved dimension, mastery risk hoặc re-plan proposal. Mọi failure từ recall đến transfer đều có thể tạo một phiên ôn có giới hạn; không tự áp lịch.
- Không evidence hợp lệ thì status là `insufficient_evidence`; không cập nhật Knowledge State.

### Knowledge State

- Level rời rạc: `no_evidence`, `recognition`, `conceptual`, `application`, `transfer`, `retained`.
- Mỗi snapshot tham chiếu evidence IDs, có confidence `low|medium|high`, retention và misconception.
- Không trung bình để recall che transfer; hint cao không được tạo `transfer/retained`.
- Assessment không đổi lịch. Plan chỉ đọc state/signal ở lần phân tích hoặc re-plan tiếp theo.

### Reflect signal

- Chỉ nhận structured signal có cause allow-list.
- `duration_factor` bị clamp 0.75-1.5; `follow_up_minutes` 0-180.
- Signal không được áp dụng cho quá khứ hoặc tự thay lịch; luôn qua Plan preview/confirm.

## Quyết định

- Giữ workflow `understanding` để tương thích API cũ, nhưng Do checkpoint dùng chung assessment engine.
- Closed item được chấm deterministic theo item type; câu mở dùng LLM + validator để tạo structured planning signal.
- Giảng viên duyệt thiết kế câu hỏi/rubric, không duyệt từng câu trả lời sinh viên. Tín hiệu chưa chắc chắn được hỏi kiểm chứng có giới hạn rồi giữ ở trạng thái unknown/abstained.
- UI sinh viên chỉ hiện câu hỏi, gợi ý, xác nhận đã ghi nhận cho Plan và hành động tiếp theo; không hiện báo cáo LLM, điểm chẩn đoán, confidence hay rubric nội bộ.
- Mỗi môn dùng ngân hàng năm stage cùng một KC: Recall → Explain → Why → Application → Transfer; giảng viên duyệt câu hỏi/rubric trước khi sinh viên nhận câu.
- Không công bố mastery probability hoặc hiệu quả học tập khi chưa có calibration/pilot.
- Bảng session/probe additive được tạo qua initialize_database/create_all. Không sửa bảng hiện có; production cần deploy/migration governance và kiểm tra PostgreSQL concurrency riêng.
- Model timeout cho phép retry; malformed/không đủ evidence thì abstain, không coi là đáp án sai và không chuyển sang hàng chờ giảng viên.
