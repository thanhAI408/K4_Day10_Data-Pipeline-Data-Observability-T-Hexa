# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
| --- | --- |
| Khóa/Lớp | K4 |
| Tên nhóm | T-Hexa |
| Repository | https://github.com/thanhAI408/K4_Day10_Data-Pipeline-Data-Observability-T-Hexa |
| Ngày hoàn thành | 2026-08-06 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Nguyễn Văn Thành | 2A202601030 | Lead — Role 1: Pipeline Integration & Release | `src/core/`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`, tích hợp và release |
| 2 | Nguyễn Hoàng Hải | 2A202601426 | Role 2: Ingestion Owner | `src/ingestion/crossref.py`, raw response, raw records và lineage |
| 3 | Nguyễn Duy Khánh | 2A202601530 | Role 3: Cleaning & Corruption Owner | `src/ingestion/cleaning.py`, `src/ingestion/corruption.py`, clean/corrupted/repaired datasets |
| 4 | Ngô Xuân Ninh | 2A202601068 | Role 4: RAG & Agent Owner | `src/retrieval/`, MiniLM, ChromaDB, search, lookup và agent |
| 5 | Nguyễn Chiến Thắng | 2A202601734 | Role 5: Evaluation & Observability Owner | `src/evaluation/`, `src/observability/`, test set, metrics, quality/freshness và reports |

## 2. Tóm tắt kết quả

Nhóm đã hoàn thành pipeline end-to-end từ Crossref đến cleaning, embedding, ChromaDB, evaluation, data observability, corruption và repair. Baseline sử dụng 24 bài báo và 18 câu hỏi cố định. Embedding được tạo bằng `sentence-transformers/all-MiniLM-L6-v2`, retrieval dùng `top_k=4`. Baseline đạt `retrieval_hit_rate=1.0000`, `mean_token_f1=0.7687`, `judge_accuracy=0.6667` và `mean_judge_score=3.8889`; quality và freshness đều đạt trạng thái tốt.

Corruption dùng seed 1337, gồm xóa 4 records mới nhất, làm rỗng 3 summaries, thêm nhiễu vào 3 summaries, cắt ngắn 2 titles, làm cũ 2 publication dates và thêm 2 duplicate rows. Sau corruption, quality report thất bại với 2 duplicate IDs, 3 missing summaries, 3 short summaries và 2 stale rows; `retrieval_hit_rate` giảm còn 0.3333. Repair được thực hiện bằng cách nạp lại raw snapshot bất biến và chạy cleaning lại, không chỉnh tay corrupted data hoặc metrics. Toàn bộ metrics và quality/freshness sau repair phục hồi đúng bằng baseline.

Giới hạn chính là agent demo bị bỏ qua do không cấu hình `GOOGLE_API_KEY`; Ragas chưa được bật bằng `RUN_RAGAS=1`.

## 3. Kiến trúc và luồng dữ liệu

```text
Crossref REST API
    -> raw response + parsed raw records
    -> cleaning và data modeling
    -> MiniLM embeddings + ChromaDB baseline index
    -> fixed evaluation set
    -> baseline metrics + quality/freshness
    -> controlled corruption
    -> corrupted index + re-evaluation
    -> repair từ immutable raw snapshot
    -> repaired index + re-evaluation
    -> comparison report
```

| Khối | Input | Xử lý chính | Output/artifact | Owner |
| --- | --- | --- | --- | --- |
| Ingestion | Crossref `/works` | Query, filter, retry/backoff, parse DOI/title/abstract/authors/dates/URLs | `data/raw/` | Nguyễn Hoàng Hải |
| Cleaning | `list[PaperRecord]` | Normalize, parse date, dedupe, helper fields, `age_days`, `text_for_embedding` | `data/clean/` | Nguyễn Duy Khánh |
| Embedding/index | Clean DataFrame | MiniLM normalized vectors, Chroma cosine index, metadata manifest | `data/embeddings/`, `data/chroma/` | Ngô Xuân Ninh |
| Evaluation | Corpus + fixed test set | Exact lookup, semantic retrieval, hit rate, token F1, judge | `data/eval/`, `data/results/` | Nguyễn Chiến Thắng |
| Observability | DataFrame ở ba trạng thái | Row count, uniqueness, completeness, summary length, stale rows | `data/quality/`, `data/reports/` | Nguyễn Chiến Thắng |
| Corruption/repair | Clean baseline + raw snapshot | Drop/blank/noise/truncate/stale/duplicate; re-clean raw để repair | Corruption log và repaired artifacts | Nguyễn Duy Khánh |
| Orchestration | Toàn bộ module | Điều phối thứ tự chạy, prerequisite, fixed test set, separate collections | Metrics và reports end-to-end | Nguyễn Văn Thành |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Cấu hình | Giá trị |
| --- | --- |
| `LLM_PROVIDER` | `gemini` theo default; agent demo bị skip vì thiếu key |
| `LLM_MODEL` | `gemini-2.5-flash` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Crossref records | 24 |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày |
| Corruption seed | 1337 |
| Collections | `papers-baseline`, `papers-corrupted`, `papers-repaired` |

```bash
uv sync
uv run --python 3.12 python script/run_phase1.py
uv run --python 3.12 python script/run_corruption_flow.py
```

| Lệnh | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Baseline pipeline | Thành công | `data/results/baseline_metrics.json`, `data/reports/phase1_report.md` |
| Corruption flow | Thành công | `data/results/corruption_log.json`, `data/reports/corruption_report.md` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Source | Crossref REST API — `https://api.crossref.org/works` |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:2026-02-07,has-abstract:true` |
| Snapshot sử dụng | Lần chạy ngày 2026-08-06 |
| Records | 24 |
| Retry/backoff | Tối đa 5 lần; retry 429/503; exponential backoff tối đa 30 giây |
| Stable ID | DOI lowercase làm `paper_id` |

### Schema chính

| Trường | Kiểu | Bắt buộc | Ý nghĩa/xử lý |
| --- | --- | --- | --- |
| `paper_id` | string | Có | DOI ổn định; bỏ record nếu thiếu |
| `title` | string | Có | Normalize whitespace; bỏ record rỗng |
| `summary` | string | Quality gate | Abstract bỏ JATS tags; kiểm tra thiếu/ngắn |
| `authors`, `categories` | list[string] | Không | Tạo `authors_joined`, `categories_joined` |
| `published`, `updated` | ISO date string | Không | Parse ngày và tính `age_days` |
| `text_for_embedding` | string | Có ở clean | Ghép title, summary, authors, categories, published |

Trong lần chạy này raw count và clean count đều là 24, không có record bị loại hoặc dedupe. `paper_id` giữ nguyên xuyên suốt raw, clean, index và evaluation. Chroma record ID có dạng `<paper_id>::<row_index>`.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
| --- | --- |
| Số câu hỏi | 18 |
| `question_type` | `summary`, `authors`, `date`, `categories` |
| Ground truth IDs | `ground_truth_doc_ids=[paper_id]` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store | ChromaDB persistent, cosine distance |
| `top_k` | 4 |
| Answer logic | Exact-title lookup được ưu tiên, sau đó semantic search |
| Judge | Structured LLM nếu khả dụng; fallback từ token F1 nếu không có provider |
| Fixed test set | `data/eval/test_set.json` dùng chung cho cả ba trạng thái |

Giữ nguyên test set giúp phép so sánh chỉ phản ánh thay đổi của corpus. Nếu tạo lại test set sau corruption, ground truth có thể bị thay đổi và làm sai lệch kết luận.

## 7. Kết quả baseline

| Artifact | Đường dẫn | Trạng thái |
| --- | --- | --- |
| Raw response/records | `data/raw/` | Có |
| Clean dataset | `data/clean/papers_clean.csv`, `.json` | Có — 24 rows |
| Embedding/index | `data/embeddings/`, `data/chroma/` | Có |
| Evaluation set | `data/eval/test_set.json` | Có — 18 questions |
| Metrics/answers | `data/results/baseline_metrics.json`, `baseline_answers.json` | Có |
| Quality/freshness | `data/quality/baseline_quality.json`, `freshness_report.json` | Có |
| Baseline report | `data/reports/phase1_report.md` | Có |

| Metric | Giá trị | Diễn giải |
| --- | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | Ground-truth document xuất hiện trong top-k cho 18/18 samples |
| `mean_token_f1` | 0.7687 | Mức trùng token khá cao với ground truth |
| `judge_accuracy` | 0.6667 | 12/18 answers được đánh giá materially correct |
| `mean_judge_score` | 3.8889/5 | Chất lượng trung bình ở mức khá |
| Ragas | N/A | Chưa bật `RUN_RAGAS=1` |

## 8. Data quality và freshness

| Check | Kỳ vọng | Baseline | Bằng chứng |
| --- | --- | --- | --- |
| Row count | > 0 | Pass: 24 | `baseline_quality.json` |
| `paper_id` unique | 0 duplicate | Pass: 0 | `baseline_quality.json` |
| Missing title | 0 | Pass: 0 | `baseline_quality.json` |
| Missing summary | 0 | Pass: 0 | `baseline_quality.json` |
| Summary < 50 chars | 0 | Pass: 0 | `baseline_quality.json` |
| Stale rows > 180 days | 0 | Pass: 0 | `baseline_quality.json` |

Baseline freshness: latest `2026-08-01`, oldest `2026-02-12`, 5 ngày kể từ latest, 0 stale rows và trạng thái **FRESH**.

## 9. Corruption scenarios và repair

| Corruption | Cách tạo | Count | Tác động thực tế | Repair |
| --- | --- | ---: | --- | --- |
| Drop latest | Xóa records mới nhất | 4 | Coverage/retrieval giảm | Reload raw và clean lại |
| Blank summary | Gán summary rỗng | 3 | 3 missing, 3 short summaries | Re-clean raw |
| Noise summary | Prefix `<<<NOISE>>>` | 3 | Token F1/judge giảm | Re-clean raw |
| Truncate title | Cắt còn 8 ký tự | 2 | Exact lookup và relevance xấu đi | Re-clean raw |
| Stale date | Trừ 730 ngày | 2 | 2 stale rows, freshness fail | Re-clean và tính lại `age_days` |
| Duplicate | Copy rows | 2 | 2 duplicate IDs | Dedupe trong cleaning |

`data/results/corruption_log.json` ghi seed, số operation, baseline row count 24 và final row count 22. Repair nạp lại `data/raw/crossref_records.json`, không dùng corrupted DataFrame làm nguồn.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Δ corruption | Phục hồi |
| --- | ---: | ---: | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1.0000 | 0.3333 | 1.0000 | -0.6667 | 100% |
| `mean_token_f1` | 0.7687 | 0.2628 | 0.7687 | -0.5059 | 100% |
| `judge_accuracy` | 0.6667 | 0.4444 | 0.6667 | -0.2222 | 100% |
| `mean_judge_score` | 3.8889 | 2.8889 | 3.8889 | -1.0000 | 100% |
| Quality | OK | FAILED | OK | 2 duplicate, 3 missing, 3 short, 2 stale | 100% |
| Freshness | FRESH | NOT FRESH | FRESH | 2 stale rows | 100% |

1. Drop latest kết hợp title/summary corruption làm corpus mất coverage và context bị hỏng, kéo `retrieval_hit_rate` giảm 0.6667 và `mean_token_f1` giảm 0.5059.
2. Re-clean từ immutable raw snapshot phục hồi uniqueness, completeness và freshness; toàn bộ repaired metrics trùng baseline.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Máy mặc định dùng Python 3.14 trong khi project hỗ trợ Python 3.11–3.13; `uv` ban đầu chưa có. Agent demo báo thiếu `GOOGLE_API_KEY`.
- **Nguyên nhân:** Sai interpreter và thiếu credential của provider mặc định.
- **Cách xử lý:** Chọn Python 3.12, chạy bằng `uv run --python 3.12`; agent demo được skip có kiểm soát và ghi artifact thay vì chặn ETL/evaluation.
- **Cách xác minh:** Hai pipeline chạy hoàn tất, metrics/reports được sinh; `agent_demo_answers.json` ghi trạng thái skip.

## 12. Giới hạn và hướng cải thiện

| Giới hạn | Ảnh hưởng | Hướng cải thiện |
| --- | --- | --- |
| Không có API key ở lần chạy cuối | Agent demo không chạy; judge có thể dùng fallback | Cấu hình provider và so sánh LLM judge với fallback |
| Ragas chưa bật | Chưa có context precision/recall và faithfulness | Chạy `RUN_RAGAS=1` cho cả ba trạng thái |
| Corpus 24 papers | Kết luận mới đúng ở quy mô lab | Tăng dữ liệu và dùng stratified test set |
| Corruption cố định | Chưa mô phỏng schema drift/partial update | Thêm corruption scenarios và validation tests |
| Chroma binaries được commit | Repo nặng, khó review | Ignore/rebuild `data/chroma/`, chỉ commit manifest/report |
| Drop log chưa lưu đầy đủ paper IDs | Lineage operation chưa tối ưu | Ghi before/after IDs cho từng corruption |

## 13. Kết luận và checklist

Pipeline đã chứng minh rõ data quality ảnh hưởng trực tiếp đến RAG. Baseline đạt retrieval coverage tuyệt đối trên test set; corruption làm giảm retrieval và answer metrics; repair từ raw snapshot phục hồi hoàn toàn.

- [x] Có 5 thành viên, vai trò và ownership rõ ràng.
- [x] Baseline chạy end-to-end.
- [x] Corruption flow chạy sau baseline.
- [x] Dùng cùng test set và `top_k` cho ba trạng thái.
- [x] Có raw, clean, embeddings, eval, results, quality và reports.
- [x] Có corruption log và repaired artifacts.
- [x] Metrics trong report khớp JSON artifacts.
- [x] Không chứa API key hoặc secret.
- [x] Có báo cáo riêng cho từng thành viên.
