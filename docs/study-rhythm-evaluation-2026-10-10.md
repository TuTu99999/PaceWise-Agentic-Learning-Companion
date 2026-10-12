# Nhịp học cá nhân và độ tin cậy phiên — 10/10/2026

Bản nối tiếp: [Nhịp theo môn/loại hoạt động, rule v2 và evaluation mới](activity-rhythm-evaluation-2026-10-10.md). Các số liệu/rule v1 dưới đây là kết quả của lần triển khai trước, không thay thế báo cáo v2.

Scope vẫn là **Plan → Do → Reflect**. Assessment ở bên trong Do; không có agent hoặc tab nghiệp vụ thứ tư.

Trạng thái: triển khai kỹ thuật các bước 1–4, đã kiểm thử offline; bước 5 mới có cơ chế thu thập/so sánh, **chưa có pilot sinh viên thật**. Không tuyên bố đã tìm được khoảng tập trung tối ưu hoặc cải thiện learning outcome.

## 1. Đã thay đổi gì?

### Estimate công việc khác với độ dài một phiên

- Không lấy lịch sử môn/bài khác làm hệ số tăng thời lượng cho mọi task.
- Chỉ dùng lịch sử cùng task và cùng ngữ cảnh gần nhất: trạng thái kiến thức nền, session/break preference. Cần ít nhất 3 phiên riêng biệt, hoàn thành, nguồn timer, không gián đoạn/unknown gap, không blocker.
- Phiên tự khai báo, thiếu provenance, bận đột xuất hoặc có thời gian checkpoint chưa tách khỏi thời gian làm việc không được dùng để hiệu chỉnh hệ số công việc.
- Legacy mastery dạng số/nhãn không có `source_evidence_ids` không được dùng để kết luận yếu kiến thức rồi cộng thời gian. Knowledge State có nguồn vẫn có thể đề xuất ôn prerequisite, với evidence và số phút ôn hiển thị riêng.
- Reflect signal không có task ID không được áp dụng đồng loạt. Signal về gián đoạn/capacity làm thay đổi khả năng xếp lịch, không suy ra cần học lâu hơn.
- Không nhân chồng hệ số lịch sử và Reflect cho cùng một sai lệch; không làm tròn tăng từng milestone nhỏ lên 15 phút.
- Khi chưa đủ dữ liệu: giữ baseline sinh viên nhập và trả `insufficient_evidence`. P50/P80 là heuristic có bất định, **không phải phân vị đã được calibration**.
- UI gom đề xuất vào “Có N đề xuất thời lượng — Xem chi tiết”, có baseline → proposed, số phút ôn, source refs và số phiên hợp lệ. Bản nháp không tự đổi estimate gốc hoặc lịch đã xác nhận.
- Lỗi capacity nêu tên bài, phút còn thiếu, giờ/phút deadline và cách xử lý. Lỗi dependency nêu milestone liên quan. Hard constraint vẫn chặn xác nhận.

Code: [plan_intelligence.py](../src/services/plan_intelligence.py), [planning.py](../src/services/planning.py), [PlanDraftNotice.tsx](../frontend/pacewise/src/components/domain/PlanDraftNotice.tsx).

### Bước 1 — Quan sát phiên đáng tin

- Timer checkpoint lưu ở backend, dùng đồng hồ server; client không gửi số giây muốn cộng.
- Pause/resume không cộng khoảng đã pause. Reload phục hồi checkpoint ở trạng thái paused, không cộng thời gian vắng mặt, không tự chạy lại.
- Heartbeat 20 giây; gap quá 45 giây chuyển sang paused/unknown và giữ checkpoint đã xác nhận. Khoảng không quan sát được không phải “không hiểu” hoặc “bỏ học”.
- Không có timeout dựa trên chuột/bàn phím hay `visibilitychange`: đọc PDF không click vẫn có thể được ghi nhận. Nếu trình duyệt suspend/throttle nền khiến mất heartbeat, chỉ ghi gap unknown, không kết luận bỏ học.
- Note được checkpoint cùng phiên; recover không xóa note.
- Command có event key và version CAS. Retry cùng nội dung không cộng lại thời gian, không ghi lại completion. Stale tab/reused key khác nội dung trả 409.
- Receipt giữ 30 command gần nhất; retry cũ ngoài cửa sổ bị chặn bằng version, không cộng lại.
- Một learner chỉ có một phiên active; có link quay lại đúng block đang dở khi mở ca khác. Hủy cho phép bắt đầu lại block; completion không bị ghi trùng khi reload.
- Có phân quyền learner/institution/course, student-only mutation và CSRF. Đi qua lớp encrypted API hiện có. Không đưa cookie/token vào dữ liệu timer.
- Ghi giờ học ngoài timer là `self_report`, không ngụy trang thành timer evidence.

**Giới hạn quan sát:** heartbeat chứng minh app có thể liên lạc, không chứng minh người học đang tập trung. Sai số giữa checkpoint và sự kiện đóng/mất kết nối không được diễn giải thành năng lực; recovery bảo thủ có thể bỏ phần thời gian chưa được xác nhận. Mất mạng ngắn trong tolerance không có độ chính xác tuyệt đối đến từng giây. Đây không phải phần mềm giám sát sự chú ý.

Code: [study_sessions.py](../src/services/study_sessions.py), [API](../src/api/study_sessions.py), [useDurableStudyTimer.ts](../frontend/pacewise/src/hooks/useDurableStudyTimer.ts).

### Bước 2 — Reflect ngắn

- Nguyên nhân: không gián đoạn, việc đột xuất, mệt, khó nội dung, học ngoài hệ thống hoặc chưa rõ.
- Cuối Do hỏi cảm nhận độ dài: chưa báo cáo, phù hợp, dài, quá dài; cùng tiến độ/blocker.
- Mở form kết thúc sẽ pause timer, không tính thời gian điền Reflect vào thời gian phiên.
- Việc đột xuất được giữ dấu trong observation kể cả sau khi resume. Không hạ Knowledge State chỉ vì bận, timer ngắn hoặc self-report.
- Các câu Reflect hỏi tiến độ/quá trình; Assessment mới kiểm tra Recall/Explain/Application/Transfer/Retention. Timer/Reflect không tự sinh điểm mastery.

Code: [StudySessionPage.tsx](../frontend/pacewise/src/pages/student/StudySessionPage.tsx), [ReflectPage.tsx](../frontend/pacewise/src/pages/student/ReflectPage.tsx).

### Bước 3 — Đề xuất nhịp bằng rule, có xác nhận

- Rule `rhythm-rule-v1`: ít nhất 3 phiên cùng môn, task, readiness, rhythm và checkpoint budget; không unknown gap, không việc đột xuất, không tự khai báo thời gian.
- Nếu đã học ít nhất 75% độ dài preference và nhiều lần báo dài/quá dài: đề xuất thử giảm 15 phút, thấp nhất 20 phút; không tự tăng nhịp.
- Dùng tối đa 5 phiên gần nhất của nhóm phù hợp, source IDs riêng biệt. Không đủ dữ liệu thì abstain, giữ preference.
- Assessment chờ duyệt/provisional/low confidence hoặc dùng hint không được coi là bằng chứng độc lập. Tổng hợp latest accepted attempt theo từng KC; KC khác trả lời đúng không che lỗi của KC còn yếu.
- Thiếu Assessment nghĩa là chất lượng học `unknown`, không phải 0 điểm hoặc đã hiểu.
- Settings có nút xác nhận. GET proposal không ghi preference/lịch; confirm recheck evidence, trả lựa chọn để workspace versioned autosave lưu. Confirm không tự áp dụng kế hoạch.

Các ngưỡng **3 phiên / 75% / giảm 15 phút / 20–45 giây** là lựa chọn kỹ thuật versioned, chưa có dữ liệu thật chứng minh tối ưu. Không cần LLM để tính nhịp này.

Code: [study_rhythm.py](../src/services/study_rhythm.py), [RhythmProposalCard.tsx](../frontend/pacewise/src/components/domain/RhythmProposalCard.tsx).

### Bước 4 — Nối scheduler

- Scheduler dùng session/break preference. Đổi nhịp chia công việc thành ca nhỏ hơn, không giảm tổng công việc.
- Có checkpoint budget thêm 0/5/10/15 phút. Mặc định 0 nếu estimate công việc đã bao gồm kiểm tra; không tự cộng đại trà.
- Budget thêm nằm trong ca: `duration = workMinutes + checkpointMinutes`. Capacity tính cả budget; tổng target công việc giữ riêng.
- Break được chừa giữa các ca. Thời gian làm việc/checkpoint không vượt deadline chính xác đến phút.
- P80 capacity thêm overhead conservative và có cảnh báo; không biến uncertainty thành cam kết chắc chắn.
- Preference mới chỉ tác động khi phân tích lịch mới. Sinh viên xem preview/diff và xác nhận; plan hiện tại, lịch quá khứ, LMS và pinned intent không bị tự đổi.

## 2. Test và output thực tế

Tất cả ca dưới là fixture kỹ thuật/synthetic, không phải quan sát sinh viên thật.

| Acceptance | Output đã kiểm tra | Evidence |
|---|---|---|
| Đóng/reload không cộng vắng mặt | Checkpoint 120 giây; recover sau 10 giây vẫn 120, status paused | `test_reload_does_not_count_absence_even_for_short_gap` |
| Mất mạng dài không suy ra yếu kiến thức | Gap 8 giờ vẫn 120 giây, interruption unknown, không có mastery inference | `test_network_gap_never_adds_absence_and_does_not_infer_misunderstanding` |
| Retry không trùng | Hai request checkpoint cùng key/body trả cùng row; complete retry chỉ có một history/event | `test_retry_after_response_loss_does_not_add_time_or_duplicate_completion` |
| Bận đột xuất không giảm Knowledge State | Snapshot relation vẫn application; history đánh dấu unexpected | Test completion API trên |
| Đọc PDF không tự coi bỏ học | Không click; heartbeat sau 20 giây: 120 → 140, vẫn running/none | `test_reading_pdf_without_clicks_is_not_automatically_interrupted` |
| Thiếu evidence không kết luận | History sparse/duplicate/unrelated/interrupted/self-report: P50 30 giữ 30; proposal null | `test_sparse_interrupted_other_task_or_duplicate_history_preserves_baseline` và các test provenance |
| Đổi nhịp không giảm việc | Target 90, ca 30 nghỉ 10: tổng work vẫn 90, mọi end ≤17:00 | `test_shorter_rhythm_keeps_work_and_breaks_do_not_cross_deadline` |
| Checkpoint không ăn mất work | 60 work, ca tối đa45 + checkpoint5, nghỉ10: cửa sổ60 phút infeasible; cửa sổ120 phút có work60 + checkpoint10 | `test_checkpoint_is_extra_capacity_not_stolen_work_and_can_make_deadline_infeasible` |
| Chưa xác nhận không áp dụng | GET giữ workspace; confirm chỉ lựa chọn; plan ID vẫn giữ nguyên | `test_rhythm_never_auto_applies_and_confirmation_rechecks_current_preferences`, browser QA |
| Không che lỗi bằng KC khác / hint | KC1 application failed + KC2 passed vẫn failed; pending/hinted pass không xóa lỗi | `test_assisted_pending_and_missing_assessment_are_not_independence_evidence` |
| Không lẫn phản hồi ca cũ vào ca mới | Response chậm của b1 sau chuyển b2 không đổi session/elapsed b2 | `useDurableStudyTimer.test.tsx` |
| Mobile/desktop không đổ 11 đoạn lên lịch | Details đóng mặc định, lỗi tên bài + thiếu15 phút trước12:00, nút áp dụng disabled | Browser QA ở390 và1366px |

Kết quả suite:

- Backend: **631 passed** — [JUnit](../evals/reports/study-rhythm-backend-2026-10-10.xml).
- Frontend: **300 passed**, 67 test files — [JUnit](../evals/reports/study-rhythm-frontend-2026-10-10.xml).
- Browser end-to-end bằng API fixture: **12/12** — [JSON](../evals/reports/study-rhythm-ui-2026-10-10/results.json), [mobile](../evals/reports/study-rhythm-ui-2026-10-10/390-draft.png), [desktop](../evals/reports/study-rhythm-ui-2026-10-10/1366-draft.png). Có thêm kiểm tra chuyển ca qua SPA không mang completion/timer cũ sang ca mới.
- Responsive regression: **43/43** — [JSON](../evals/reports/responsive-ui-2026-10-09/results.json).
- Calendar wheel/touch: **6/6**, student và instructor ở390×844,662×432,844×390. Mọi case chạm được giờ cuối lịch; không bị bottom navigation chặn.
- Deterministic agent evaluation: dataset `2026-10-10.v4`, `overall_pass=true` — [JSON](../evals/reports/study-rhythm-agent-evaluation-2026-10-10.json). Các metric1.0 là trên golden fixture, **không phải accuracy LLM trên người học thật**.
- `npm run build` / TypeScript thành công. Docker backend/frontend rebuild; `/health` và `/app` trả200, bảng `pacewise_study_timer_sessions` có `active_scope`. Timer API không qua encrypted transport trả426; qua internal encrypted dispatch nhưng không có session trả401. Không đọc/chỉnh dữ liệu sinh viên thật để thử.

Lệnh chạy lại (PowerShell, repo root):

```powershell
$env:APP_ENV = 'test'
$env:PRIVATE_API_REQUIRED = 'false'
$env:LANGSMITH_ENABLED = 'false'
$env:DATABASE_URL = 'sqlite:///./evals/reports/rhythm-test-' + [guid]::NewGuid().ToString('N') + '.db'
.venv/Scripts/python.exe -m pytest tests -q --junitxml=evals/reports/study-rhythm-backend-2026-10-10.xml
.venv/Scripts/python.exe -m evals.run_agent_eval --output evals/reports/study-rhythm-agent-evaluation-2026-10-10.json
```

Ở `frontend/pacewise`:

```powershell
npm.cmd test -- --reporter=default --reporter=junit --outputFile=../../evals/reports/study-rhythm-frontend-2026-10-10.xml
npm.cmd run build
```

Browser QA cần Vite ở5174 và Playwright có Edge, ví dụ `PLAYWRIGHT_MODULE` trỏ package Playwright local; chạy `node scripts/evaluate_study_rhythm_ui.cjs`, `node scripts/evaluate_responsive_ui.cjs`, `node scripts/evaluate_calendar_scroll.cjs`. Chỉ dùng account/API fixture synthetic, không gửi LLM request.

## 3. Pilot — đã chuẩn bị cơ chế, chưa hoàn tất

Sau user confirm, lưu event `RHYTHM_TRIAL_ACCEPTED` với policy/source refs. API so sánh mô tả cùng learner/course/task/readiness, trước và sau thời điểm xác nhận.

Metric: số phiên tương đồng, completion rate, tỷ lệ báo dài, median recorded minutes; từng dimension Assessment có số phiên đã test và pass rate. Không test thì `null`, không lấy timer làm proxy hiểu bài. Ít hơn3 phiên mỗi phía: `collecting`; đủ mẫu: `descriptive_not_causal`.

Pilot thật cần:

1. Xin consent; chọn task/session tương đồng, giảng viên kiểm tra mapping/readiness và rubric.
2. Thu baseline; không pooling môn khác để đủ sample.
3. Cho người học xác nhận một thay đổi nhỏ; giữ workload và deadline như trước.
4. Đối chiếu tiến độ, interruption, feeling và independent application/transfer; thêm delayed retention.
5. Kiểm tra confounding của độ khó/stage, thời điểm và deadline. Hiệu chỉnh ngưỡng, version policy; có thể revert preference khi user muốn.
6. Chỉ tuyên bố hiệu quả giáo dục sau thiết kế đánh giá phù hợp và đủ dữ liệu. Không dùng golden/synthetic case làm chứng minh causal improvement.

Chưa kiểm chứng tải1.000 sinh viên hoặc cost/latency ở production trong lần sửa này. Heartbeat là một nguồn tải mới cần load test riêng.

## 4. Cách thử trên local

1. Reload PaceWise. Với bản nháp cũ đang lưu, bấm **phân tích lại** để dùng estimate policy mới; không tự áp dụng/cắt công việc từ draft cũ.
2. Từ ca đã xác nhận, mở Do → start → chọn “việc đột xuất” → pause → reload → timer vẫn ở checkpoint paused.
3. Resume → hoàn thành → báo độ dài phiên → lưu. Xem Reflect để phân tích tiến độ, không chấm lại kiến thức.
4. Settings → Nhịp học. Cold start sẽ giữ preference; không cố generate đề xuất khi thiếu3 phiên phù hợp.
5. Khi có đề xuất, xem nguồn và xác nhận. Lịch đã áp dụng chưa đổi; muốn đổi lịch phải phân tích, xem preview, xác nhận riêng.

Không thêm dependency/LLM call cho quyết định nhịp; không dùng thử nghiệm này để tự ghi điểm hay thay lịch Canvas.
