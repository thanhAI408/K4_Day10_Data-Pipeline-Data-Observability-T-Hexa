# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Hoàng Hải |
| MSSV | 2A202601426 |
| Khóa/Lớp | K4 |
| Tên nhóm | T-Hexa |
| Vai trò chính | Role 2: Ingestion Owner |
| Repository | https://github.com/thanhAI408/K4_Day10_Data-Pipeline-Data-Observability-T-Hexa |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Phần việc chính | `src/ingestion/crossref.py`, `data/raw/` | Artifact/module từ bước trước | Module và artifact đúng contract | Hoàn thành |
| Handoff và tích hợp | Contract chung của nhóm | Raw/clean/index/test set tùy role | Output để pipeline kế tiếp sử dụng | Hoàn thành |

Tôi chịu trách nhiệm chính về fetch Crossref, retry/backoff, parse payload thành `PaperRecord`, lưu raw response và parsed snapshot có thể truy vết. Ownership trong báo cáo này chỉ áp dụng cho phạm vi role đã được nhóm phân công; kết quả end-to-end là kết quả tích hợp chung của cả nhóm.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Kiểm tra contract và integration | Các role phụ thuộc trực tiếp | Schema, paths và function signatures tương thích |
| Đối chiếu artifacts/metrics | Pipeline end-to-end | Report khớp với JSON outputs thực tế |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Hoàn thiện phần việc của role | `src/ingestion/crossref.py`, `data/raw/` | `data/raw/crossref_response.json` và `data/raw/crossref_records.json` chứa 24 records. | Chạy baseline và corruption flow |
| Bảo đảm integration contract | `src/`, `data/` | Output được module kế tiếp sử dụng | Kiểm tra artifacts và metrics |
| Đóng góp bằng chứng báo cáo | `data/results/`, `data/quality/`, `data/reports/` | Kết luận có số liệu đối chiếu | Mở JSON/Markdown artifacts |

**Output cụ thể:** `data/raw/crossref_response.json` và `data/raw/crossref_records.json` chứa 24 records.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Phần việc cần biến dữ liệu hoặc artifact đầu vào thành output có schema ổn định, có thể truy vết và có thể được module kế tiếp sử dụng mà không phải đoán field, đường dẫn hay trạng thái.

### Cách triển khai

Fetch crossref, retry/backoff, parse payload thành `paperrecord`, lưu raw response và parsed snapshot có thể truy vết. Việc triển khai tuân theo `Settings.paths`, giữ stable `paper_id`, không hard-code secret và luôn tạo artifact để kiểm chứng. Các trạng thái baseline, corrupted và repaired dùng cùng evaluation set và retrieval configuration.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Artifact/module từ bước trước trong pipeline |
| Output | `data/raw/crossref_response.json` và `data/raw/crossref_records.json` chứa 24 records. |
| Module phụ thuộc | `src/core/config.py` và contract chung của nhóm |
| Module sử dụng output | Bước kế tiếp trong luồng ingestion → clean → index → evaluate → observe |
| Điều kiện lỗi | Input thiếu, schema sai, artifact không tồn tại, dữ liệu rỗng hoặc credential không khả dụng |

### Cách xác minh

```bash
uv run --python 3.12 python script/run_phase1.py
uv run --python 3.12 python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** hai flow chạy hoàn tất và tạo đủ artifacts.
- **Kết quả thực tế:** baseline 24 rows/18 samples; corrupted metrics giảm; repaired metrics trùng baseline.
- **Artifact/log:** `data/results/`, `data/quality/`, `data/reports/`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** cần kết quả so sánh công bằng và có thể tái hiện.
- **Các phương án:** thay đổi test set/config theo từng trạng thái; hoặc giữ nguyên test set/config và chỉ thay corpus.
- **Phương án đã chọn:** Dùng DOI lowercase làm stable `paper_id` và lưu raw response trước khi parse để bảo đảm lineage.
- **Lý do:** giảm confounding, giữ lineage và cho phép quy thay đổi metrics về data corruption/repair.
- **Bằng chứng:** baseline và repaired có cùng metrics, trong khi corrupted giảm rõ rệt.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/blocker:** Crossref có thể trả 429/503 hoặc metadata thiếu/không đồng nhất. Thêm timeout, tối đa 5 retries và exponential backoff; bỏ record thiếu DOI/title.
- **Cách xử lý:** điều chỉnh đúng tại module/flow, không sửa tay metrics hoặc answers.
- **Cách xác minh:** chạy lại hai entrypoint và kiểm tra artifact mới.
- **Điều học được:** pipeline đáng tin cậy phải có error handling, artifact lineage và trạng thái skip/fail minh bạch.

## 7. Hiểu biết về luồng end-to-end

1. Crossref được gọi với query/filter; raw response và parsed records được lưu. Cleaning chuẩn hóa dữ liệu, dedupe, tính `age_days` và tạo `text_for_embedding`. MiniLM biến text thành vectors và ChromaDB lưu corpus.
2. Test set chứa question, ground truth và `ground_truth_doc_ids`. Retrieval hit kiểm tra tài liệu đúng có trong top-k; token F1 và judge đánh giá câu trả lời.
3. Quality checks đo completeness, uniqueness, validity và summary length; freshness tập trung vào tuổi dữ liệu và stale rows.
4. Dùng cùng test set giúp so sánh công bằng, tránh thay đổi đề bài/ground truth giữa ba trạng thái.
5. Repair thành công khi repaired dataset lấy lại schema/quality/freshness và metrics trở lại gần hoặc bằng baseline.

## 8. Phân tích kết quả

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.3333 | 1.0000 | Corruption làm mất coverage; repair phục hồi hoàn toàn |
| `mean_token_f1` | 0.7687 | 0.2628 | 0.7687 | Context/answer bị nhiễu mạnh rồi trở lại baseline |
| `judge_accuracy` | 0.6667 | 0.4444 | 0.6667 | Giảm 0.2222 và phục hồi hoàn toàn |
| `mean_judge_score` | 3.8889 | 2.8889 | 3.8889 | Giảm 1 điểm rồi phục hồi |
| Quality checks | OK | FAILED | OK | Corrupted có duplicate, missing/short summary và stale rows |
| Freshness | FRESH | NOT FRESH | FRESH | 2 stale rows sau corruption, 0 sau repair |

### Kết luận từ số liệu

1. Xóa records mới nhất cùng summary/title/date corruption → quality/freshness fail → `retrieval_hit_rate` giảm từ 1.0000 xuống 0.3333 và token F1 giảm từ 0.7687 xuống 0.2628.
2. Nạp lại raw snapshot và chạy cleaning/index/evaluation lại → quality/freshness trở lại OK/FRESH → toàn bộ repaired metrics bằng baseline.

Corruption ảnh hưởng rõ nhất là drop latest records kết hợp corruption title/summary, vì vừa làm mất ground-truth documents vừa làm hỏng nội dung được embed. Kết quả phục hồi hoàn toàn là hợp lý vì repair dùng đúng raw snapshot và cùng cấu hình đánh giá.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Data contract và stable IDs quyết định khả năng tích hợp giữa các module.
2. Data observability phải tạo signal trước khi lỗi dữ liệu trở thành lỗi câu trả lời.
3. Chất lượng retrieval phụ thuộc trực tiếp vào coverage và chất lượng corpus, không chỉ vào LLM.

### Nếu có thêm thời gian

Bật `RUN_RAGAS=1`, cấu hình LLM provider để chạy agent/judge đầy đủ, tăng corpus và thêm automated tests cho schema, lineage, corruption log và reproducibility.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng vai trò được phân công và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end.
- [x] Mọi kết luận đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi thành công cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo cá nhân được diễn đạt theo vai trò riêng.

**Họ và tên:** Nguyễn Hoàng Hải  
**Ngày xác nhận:** 2026-08-06
