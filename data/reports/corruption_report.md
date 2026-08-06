# Corruption & Repair — Comparison report

## Metric comparison (baseline ↔ corrupted ↔ repaired)

| Metric | Baseline | Corrupted | Δ (C − B) | Repaired | Δ (R − B) |
| --- | --- | --- | --- | --- | --- |
| `samples` | 18 | 18 | +0.0000 | 18 | +0.0000 |
| `retrieval_hit_rate` | 1.0000 | 0.3333 | -0.6667 | 1.0000 | +0.0000 |
| `mean_token_f1` | 0.7687 | 0.2628 | -0.5059 | 0.7687 | +0.0000 |
| `judge_accuracy` | 0.6667 | 0.4444 | -0.2222 | 0.6667 | +0.0000 |
| `mean_judge_score` | 3.8889 | 2.8889 | -1.0000 | 3.8889 | +0.0000 |
| `ragas` | skipped: Set RUN_RAGAS=1 to enable the slower Ragas pass. | skipped: Set RUN_RAGAS=1 to enable the slower Ragas pass. | n/a | skipped: Set RUN_RAGAS=1 to enable the slower Ragas pass. | n/a |

## Data quality

| State | Status | Rows | Duplicate IDs | Missing summary | Stale rows |
| --- | --- | --- | --- | --- | --- |
| baseline | n/a | 18 | n/a | n/a | n/a |
| corrupted | FAILED | 22 | 2 | 3 | 2 |
| repaired | OK | 24 | 0 | 0 | 0 |

## Freshness

| State | Latest | Days since latest | Stale rows | Is fresh |
| --- | --- | --- | --- | --- |
| corrupted | 2026-07-02 | 35 | 2 | no |
| repaired | 2026-08-01 | 5 | 0 | yes |

## Narrative

- The corrupted dataset intentionally drops recent rows, blanks summaries, injects noise,
  truncates titles, shifts publication dates, and duplicates records.
- A drop in `retrieval_hit_rate`, `judge_accuracy`, or `mean_judge_score` confirms
  that the agent is sensitive to data quality issues.
- The repaired dataset re-runs the cleaning pipeline from the raw snapshot; metrics
  should recover close to the baseline.
