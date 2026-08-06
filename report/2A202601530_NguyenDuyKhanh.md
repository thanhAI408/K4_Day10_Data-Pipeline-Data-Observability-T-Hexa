# Báo cáo vai trò cá nhân — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Duy Khánh |
| MSSV | 2A202601530 |
| Khóa/Lớp | K4 |
| Tên nhóm | T-Hexa |
| Vai trò chính | Observability & Reporting owner |
| Repository | `https://github.com/thanhAI408/K4_Day10_Data-Pipeline-Data-Observability-T-Hexa` |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Data quality checks | `src/observability/quality.py` — `run_data_quality_checks` | Cleaned, corrupted hoặc repaired `DataFrame`; `Settings`; tên report | Quality result dạng dictionary và JSON trong `data/quality/` | Hoàn thành implementation |
| Freshness monitoring | `src/observability/quality.py` — `build_freshness_report` | `DataFrame` có `published`, `age_days`; `Settings`; đường dẫn report | JSON gồm latest/oldest published, stale rows, total rows và `is_fresh` | Hoàn thành implementation |
| Markdown reporting | `src/observability/reporting.py` — `generate_phase1_report`, `generate_corruption_report` | Source summary, metrics, quality/freshness payloads | Baseline report và corruption comparison report trong `data/reports/` | Hoàn thành implementation |

Phạm vi báo cáo cá nhân chỉ gồm hai file `quality.py` và `reporting.py`. Các hàm này nhận payload do pipeline cung cấp, tạo tín hiệu quality/freshness và render baseline/comparison report. Các file khác chỉ được dùng ở mức runtime để cung cấp dữ liệu đầu vào và lấy metrics đối chiếu, không phải deliverable cá nhân trong báo cáo này.

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Xây dựng quality checks | `src/observability/quality.py` | Kiểm tra row count, `paper_id` null/duplicate, `title`, độ dài `summary` và freshness; kết quả có pass/fail và số lượng record lỗi | `rg -n "TODO\(student\)|NotImplementedError" src/observability/quality.py` không còn TODO; `git diff --check` đạt |
| Xây dựng freshness report | `src/observability/quality.py` | Tính ngày published mới nhất/cũ nhất, số dòng stale và trạng thái freshness; ghi JSON | Đối chiếu schema trong hàm `build_freshness_report` và quality contract |
| Xây dựng Markdown reports | `src/observability/reporting.py` | Baseline report có source/metrics/quality/freshness; comparison report có delta và recovery metric | `rg -n "TODO\(student\)|NotImplementedError" src/observability/reporting.py` không còn TODO; `git diff --check` đạt |

Output cụ thể của phần việc là contract code tạo ra các artifact sau khi pipeline gọi hàm:

- `data/quality/<report_name>.json`
- `data/quality/freshness_report.json`
- `data/reports/phase1_report.md`
- `data/reports/corruption_report.md`


## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline RAG có thể tạo index và trả lời được nhưng vẫn sử dụng dữ liệu thiếu, trùng, rỗng hoặc quá cũ. Phần observability cần biến các lỗi đó thành tín hiệu có thể đo, ghi thành artifact và so sánh giữa baseline, corrupted và repaired dataset.

### Cách triển khai

`run_data_quality_checks` thực hiện các bước sau:

1. Kiểm tra dataset không rỗng.
2. Xác định `paper_id` bị thiếu hoặc blank và kiểm tra ID có unique hay không.
3. Xác định `title` bị thiếu hoặc blank.
4. Trim `summary`, tính min/max/average length và đánh dấu summary rỗng.
5. Chuyển `age_days` sang numeric; record có `age_days` lớn hơn `settings.freshness_threshold_days` được tính là stale.
6. Gom kết quả vào `checks`, tính trạng thái tổng thể và ghi JSON qua `core.utils.write_json`.

`build_freshness_report` dùng cùng quy tắc freshness, parse `published` để lấy ngày mới nhất/cũ nhất và ghi payload có các field theo contract. Giá trị ngày sai được chuyển thành unknown thay vì làm hỏng toàn bộ report.

`reporting.py` tạo Markdown table từ payload thật. Baseline report hiển thị source summary, các metric chính, từng quality check và freshness. Comparison report tính:

- thay đổi do corruption: `corrupted - baseline`;
- recovery sau repair: `repaired - corrupted`;
- ghi chú khi metric không numeric, không có dữ liệu hoặc quay về baseline.

Comparison report nhận baseline quality/freshness cùng với hai trạng thái corrupted/repaired, để bảng so sánh không phải suy diễn baseline observability.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `pandas.DataFrame` có các cột quality như `paper_id`, `title`, `summary`, `age_days`; freshness dùng thêm `published`; metrics/source summary là dictionary |
| Output | Quality dictionary có `checks`, `passed`, `status`; freshness dictionary có `latest_published`, `oldest_published`, `stale_rows`, `total_rows`, `is_fresh`; Markdown report được ghi ra path truyền vào |
| Module phụ thuộc | `pandas`, `core.config.Settings`, `core.utils.write_json`, `core.utils.write_text` |
| Module sử dụng output | Pipeline orchestration gọi các hàm trong hai module và các artifact được ghi trong `data/quality/`, `data/reports/` |
| Điều kiện lỗi cần xử lý | DataFrame sai kiểu, cột thiếu, ID/title/summary blank, age/date không parse được, metric thiếu và quality/freshness payload không đầy đủ |

### Cách xác minh

```powershell
rg -n "TODO\(student\)|NotImplementedError" src/observability/quality.py
rg -n "TODO\(student\)|NotImplementedError" src/observability/reporting.py
git diff --check -- src/observability/quality.py src/observability/reporting.py
git status --short --branch
```

- **Kết quả mong đợi:** Các file hoàn thành không còn `TODO(student)` hoặc `NotImplementedError`, diff không có whitespace error và artifacts được sinh sau khi chạy pipeline.
- **Kết quả thực tế:** Kiểm tra tĩnh đạt; pipeline runtime đã tạo đủ artifact baseline/corrupted/repaired sau khi Python interpreter hoạt động. Commit `6cf52ac` của phần observability trước đó đã được push lên branch `2A202601530-NguyenDuyKhanh`.
- **Artifact/log:** Có `data/results/baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json`, quality/freshness JSON, `corruption_log.json`, `phase1_report.md` và `corruption_report.md` để đối chiếu.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Report cần ghi được cả kết quả và thư mục output, đồng thời phải dùng được cho baseline/corrupted/repaired flow.
- **Các phương án đã cân nhắc:** Tự gọi `mkdir`/`json.dump`/`write_text` trong từng hàm; hoặc dùng utility chung của project. Với summary report, có thể chỉ ghi một trạng thái tổng thể hoặc ghi thêm count/detail của từng check.
- **Phương án đã chọn:** Dùng `write_json` và `write_text` của `core.utils`, đồng thời trả về quality report có per-check details, counts và overall status.
- **Lý do:** Utility chung đảm bảo tạo parent directory và format JSON nhất quán. Per-check details giúp truy nguyên duplicate, missing và stale rows thay vì chỉ nhận một boolean pass/fail.
- **Bằng chứng quyết định phù hợp:** Quality report contract có `checks`, `missing_columns`, `total_rows`, `passed`, `status`; comparison report có delta/recovery và note cho dữ liệu không đầy đủ.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `python : The term 'python' is not recognized as the name of a cmdlet...`; khi thử dùng virtual environment: `No Python at '"C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe"'`.
- **Lệnh hoặc bước tái hiện:** Chạy kiểm tra syntax/runtime bằng `python -B ...` và `.venv\Scripts\python.exe -B ...`.
- **Nguyên nhân gốc:** Python launcher không có interpreter tại đường dẫn cấu hình; virtual environment hiện tại trỏ tới interpreter đã bị thiếu.
- **Cách xử lý:** Giữ nguyên source code, sau đó chạy lại pipeline khi Python 3.12 hợp lệ đã hoạt động; baseline và corruption flow hoàn tất.
- **Cách xác minh sau khi sửa:** Đối chiếu `baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json`, quality/freshness reports và `corruption_report.md`.
- **Điều học được:** Implementation code và integration runtime là hai mức hoàn thành khác nhau; chỉ kết luận metrics sau khi artifact thực tế được sinh và đối chiếu.

Nếu tiếp tục xử lý blocker:

- **Phạm vi bị ảnh hưởng:** Runtime import/test của observability module và toàn bộ baseline/corruption flow trong thời gian interpreter bị thiếu; sau khi môi trường hoạt động, flow đã được xác minh.
- **Những gì đã loại trừ:** `git diff --check` đạt và hai file phụ trách không còn TODO; lỗi hiện tại không phải do whitespace hoặc TODO. Các file ngoài phạm vi báo cáo chỉ phục vụ tạo metrics và vẫn là thay đổi local chưa commit/push.
- **Bước tiếp theo:** Có thể bổ sung test tự động và bật `RUN_RAGAS=1` nếu cần thêm Ragas metrics; các metrics chính hiện đã có artifact để điền báo cáo.

## 7. Hiểu biết về input/output của phần phụ trách

1. `quality.py` nhận `DataFrame` từ pipeline và kiểm tra completeness, uniqueness, validity của ID/title/summary cùng freshness theo `published` và `age_days`.
2. Quality và freshness là hai tín hiệu độc lập: dataset có thể không có lỗi schema nhưng vẫn stale; vì vậy cả hai report đều cần được ghi thành artifact.
3. `reporting.py` nhận source summary, evaluation metrics, quality payload và freshness payload, sau đó render bảng Markdown có giá trị thật, delta và recovery.
4. Comparison report dùng cùng bộ metrics cho baseline, corrupted và repaired để thay đổi trong bảng phản ánh trạng thái dữ liệu, không phải thay đổi contract báo cáo.
5. Trong lần chạy này, quality/freshness chuyển `PASS/FRESH → FAIL/STALE → PASS/FRESH`, còn các metrics chính giảm ở trạng thái corrupted và trở về baseline sau repair.

## 8. Phân tích kết quả

### Metrics chính

Các metrics dưới đây là kết quả tổng hợp của nhóm, được dùng làm bằng chứng runtime để kiểm tra output của hai module observability/reporting, không phải phần việc sở hữu thêm.

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.3333 | 1.0000 | bằng chứng cho việc tín hiệu dữ liệu xấu kéo giảm coverage; comparison report ghi nhận recovery hoàn toàn |
| `mean_token_f1` | 0.7687 | 0.2628 | 0.7687 | Delta 0.5059 cho thấy summary/context bị hỏng ảnh hưởng trực tiếp đến độ trùng khớp câu trả lời; repaired trở về baseline |
| `judge_accuracy` | 0.6667 | 0.4444 | 0.6667 | giảm 0.2222; quality status trong report giúp giải thích metric giảm |
| `mean_judge_score` | 3.8889 | 2.8889 | 3.8889 | -1 là tín hiệu answer quality giảm; repair recovery được thể hiện cùng các quality/freshness checks |
| Quality checks | OK | FAILED | OK | phát hiện duplicate, missing/short summary và stale rows, sau đó render trạng thái trong report |
| Freshness | FRESH | NOT FRESH | FRESH | 2 stale rows sau corruption và xác nhận dữ liệu trở lại FRESH sau repair |

### Kết luận từ số liệu

Các chuỗi nguyên nhân–bằng chứng sau được hỗ trợ bởi kết quả runtime do nhóm cung cấp:

1. Corruption làm quality chuyển từ `OK` sang `FAILED`, freshness từ `FRESH` sang `NOT FRESH`, retrieval hit rate giảm từ 1.0000 xuống 0.3333 và token F1 giảm từ 0.7687 xuống 0.2628.
2. Repair lại từ raw source → quality/freshness trở về `OK/FRESH` và các metric evaluation trở về đúng baseline.

Không thể tách riêng đóng góp của từng corruption lên từng metric vì flow áp dụng các corruption trong cùng một lần chạy. Theo phân tích của tôi, corrupted dataset làm giảm chất lượng agent và repair khôi phục kết quả.

Comparison contract trong `reporting.py` đã được mở rộng để nhận baseline quality/freshness và hỗ trợ output đủ ba trạng thái.

Các số liệu trong bảng là kết quả metrics đã được nhóm thống nhất; các artifact tương ứng nằm trong `data/results/`, `data/quality/` và `data/reports/` của nhóm.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Data pipeline cần có quality gate và artifact audit, không chỉ cần exit code của script là thành công.
2. Quality và freshness là hai tín hiệu khác nhau: uniqueness/completeness không thay thế được kiểm tra độ mới của dữ liệu.
3. Một lỗi dữ liệu chỉ có ý nghĩa với RAG khi được nối từ corruption log → quality/freshness signal → retrieval/answer metric trên cùng evaluation set.

### Nếu có thêm thời gian

Nếu có thêm thời gian, tôi sẽ viết test tự động cho các case valid/duplicate/blank/stale/missing-column và bật Ragas để bổ sung nhóm metrics đánh giá sâu hơn. Baseline–corrupted–repaired và bảng metrics chính đã được xác minh bằng artifact runtime.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu; phần chưa có dữ liệu được ghi rõ là chưa đo.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Duy Khánh  
**Ngày xác nhận:** 2026-08-06
