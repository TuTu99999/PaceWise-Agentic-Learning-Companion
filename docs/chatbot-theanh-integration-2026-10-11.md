# Chatbot sinh viên — tích hợp TheAnh và đánh giá

Đã đối chiếu `origin/TheAnh` tại `12acbd1`, đặc biệt `0059f2b` (grounded QA/công thức) và `042adab` (quota). Port có chọn lọc; không merge toàn nhánh, không ghi đè thay đổi hiện tại.

## Đã đưa vào

- Prompt theo source ID; backend điền metadata citation thật. Không tự gắn citation vào câu trả lời thiếu nguồn, không dùng đáp án hard-code cho DS201 để che lỗi model.
- Ưu tiên học liệu giải thích hơn metadata quiz; giữ ACL live, tenant/môn, version file và scope chương của Do. QA chỉ tải môn đang chọn và quyền file, không tải tasks/module tất cả môn, không embedding lại trên request.
- Ngưỡng vector tối thiểu 0,4 trước rerank. Negative thực tế: câu quang hợp trong DS201 có vector 0,336 nhưng reranker 0,997. Không cho score rerank cứu nguồn lạc môn. Ngưỡng mới chỉ kiểm tra pilot, chưa hiệu chỉnh đa môn.
- Markdown/LaTeX/KaTeX lazy-loaded; chặn HTML, ảnh từ ngoài, URL do LLM tự bịa và trusted LaTeX commands. Giữ link mở PDF mới qua cơ chế phân quyền hiện tại.
- Tối đa 6 lượt history, chỉ user/assistant; history không phải bằng chứng. Hỗ trợ query nối tiếp, chặn submit trùng và bỏ response cũ khi đổi môn/cuộc chat.
- Quota PostgreSQL dùng chung giữa process: burst/phút/giờ, token/ngày, concurrency và USD budget tùy chọn. UI tuân Retry-After, không tự lặp request tốn phí. Scope counter HMAC, không lưu IP thô.
- Không giữ DB transaction khi chờ model. Reconciliation idempotent, đúng window khi vượt nửa đêm. Usage thiếu giữ reservation; USD budget bật nhưng chưa có giá fail closed, không coi là miễn phí.
- Giữ cache theo user/tenant/course/version và model routing đã có. Không cache assessment/quyết định học tập; giữ metadata-only tracing, không bật native trace nội dung.

## Kết quả

- 239 test backend liên quan agent/chat/quota/ACL/Do/API mã hóa/telemetry/evaluation passed. Toàn frontend: 81 file, 385 test passed; TypeScript và build passed.
- Live DS201: 6/6 câu lý thuyết có citation hợp lệ theo vị trí, không phải extractive fallback. Chặn system-prompt injection, chuyển yêu cầu làm hộ sang gợi mở, từ chối quang hợp ngoài môn; tenant khác không lấy được nguồn.
- QA node latency: 5,15–12,69 giây, median 7,93 giây. Không phải p95 API end-to-end hoặc SLA production.
- PostgreSQL: 1.000 quota request giả lập/32 worker, 0 LLM calls. 24 accepted, 976 capacity-rejected. Counter không âm và slot trả hết; schema chỉ chứa bảng test đã dọn. Đây là overload protection, KHÔNG chứng minh phục vụ được 1.000 SV cùng lúc. Rejection rate cao phải được tính đến khi thiết kế queue/load test.

## RAGAS pilot: chưa đạt quality gate

| Metric | Điểm | Mẫu chấm được |
|---|---:|---:|
| Faithfulness | 0,9190 | 6/6 |
| Answer relevancy | 0,6385 | 6/6 |
| Context precision với reference | 1,0000 | 6/6 |
| Context recall | 1,0000 | 6/6 |

Judge dùng proxy/model đang cấu hình và embedding MiniLM đa ngôn ngữ local; 1 worker, relevancy strictness=1. Không bật RAGAS analytics/native trace. Các metric theo [tài liệu RAGAS](https://docs.ragas.io/en/v0.3.4/references/metrics/).

Ngưỡng nội bộ: faithfulness ≥0,8, các metric khác ≥0,7, mọi mẫu phải được chấm. Không bỏ NaN để làm đẹp trung bình. `quality_passed=false` vì relevancy <0,7; `passed=false` còn bắt buộc cho pilot kể cả khi quality đạt. Không cho copy câu hỏi trùng để làm đủ 100 mẫu.

Evaluation dùng 155.295 input +11.543 output token: tổng cho bộ judge, KHÔNG phải một câu chat. Chưa cấu hình bảng giá nên USD là `null`, không phải 0. Relevancy dùng embedding local/strictness=1; điểm cần xem cùng review từng câu, không đủ để kết luận mọi câu trả lời sai hoặc đúng.

## Hạn chế

- Citation đúng ID/trang không bảo đảm từng luận điểm được nguồn hỗ trợ; faithfulness vẫn dưới 1. Cần sửa độ tập trung/độ dài câu trả lời dựa trên lỗi từng mẫu và reference được giảng viên review.
- Chỉ DS201 có slide đủ nội dung trong pilot; không suy rộng ra 8 môn chưa nạp PDF. Cần ≥100 câu hỏi khác nhau, đa môn/chương, cả negative khó, nối tiếp, OCR lỗi, adversarial và đánh giá độc lập.
- Công thức hiển thị tốt hơn không sửa được OCR mất ký hiệu. Không port upstream render mọi trang thành ảnh không giới hạn; vision theo trang cần giới hạn/tính chi phí và test riêng.
- Ngưỡng vector/reranker chưa hiệu chỉnh đa môn/tiếng Việt. Qdrant client/server hiện lệch 1.19/1.15; truy vấn pilot chạy nhưng cần pin cặp tương thích trước production, không tắt cảnh báo để che lỗi.
- Quota/cache/routing không phải chứng minh 1.000 SV. Cần load test toàn API/graph với payload thật, p95, token/cache hit, rejection rate, DB pool và giá provider. USD budgets mặc định tắt.

## Báo cáo và chạy lại

Reports: `evals/reports/chatbot-theanh-2026-10-11/`. Dataset chỉ có câu hỏi do người phát triển viết và học liệu DS201; không có tên/email/ID hay đoạn chat thật của SV.

`run_chatbot_probe` chỉ gọi QA node/retrieval read-only, không gọi graph có checkpoint/evidence writes. `run_chatbot_quota_probe` chỉ tạo/dọn schema UUID test do chính lần chạy sinh ra. Không dùng fixture/seed vào database production.

RAGAS phải chạy trong venv evaluator riêng và cùng mạng với proxy. Dependency evaluation pin community <0,4 vì RAGAS 0,3.x dùng adapter đã bị bỏ trong 0,4. Image production không chứa evaluator/Git; nếu evaluator tạm chạy trong image đó, đặt `GIT_PYTHON_REFRESH=quiet` và không dùng experiment Git versioning.

```powershell
python -m evals.run_ragas_eval evals/datasets/chatbot-theanh-pilot-2026-10-11.jsonl --pilot --output evals/reports/ragas-pilot.json
```

Exit 1 khi quality gate không đạt là kết quả đánh giá, không phải lý do hạ threshold để báo pass.
