# Phase 1 — Baseline report

## Source summary

| Field | Value |
| --- | --- |
| API | Crossref REST API |
| Query | agentic retrieval augmented generation large language model |
| Filter | from-pub-date:2026-02-07,has-abstract:true |
| Rows ingested | 24 |
| Raw records file | `C:\Users\ASUS\Downloads\end-to-end_day10\data\raw\crossref_records.json` |
| Clean dataset | `C:\Users\ASUS\Downloads\end-to-end_day10\data\clean\papers_clean.csv` |

## Evaluation metrics

| Metric | Value |
| --- | --- |
| `samples` | 18 |
| `retrieval_hit_rate` | 1.0000 |
| `mean_token_f1` | 0.7687 |
| `judge_accuracy` | 0.6667 |
| `mean_judge_score` | 3.8889 |
| `ragas` | skipped: Set RUN_RAGAS=1 to enable the slower Ragas pass. |

## Data quality

- **Status**: OK
- Rows inspected: **24**
- Duplicate paper_ids: **0**
- Missing titles: **0**
- Missing summaries: **0**
- Short summaries: **0** (threshold 50 chars)
- Stale rows: **0**

## Freshness

- Latest published: **2026-08-01**
- Oldest published: **2026-02-12**
- Days since latest: **5**
- Stale rows: **0**
- Threshold: **180 days**
- Status: **FRESH**
