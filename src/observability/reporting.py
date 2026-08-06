from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils import write_text


METRIC_KEYS = ("samples", "retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score", "ragas")


def _format_metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, dict):
        return ", ".join(f"{k}: {_format_metric(v)}" for k, v in value.items()) or "(empty)"
    if value is None:
        return "n/a"
    return str(value)


def _metric_rows(metrics: dict[str, Any]) -> list[str]:
    rows = ["| Metric | Value |", "| --- | --- |"]
    for key in METRIC_KEYS:
        rows.append(f"| `{key}` | {_format_metric(metrics.get(key))} |")
    return rows


def generate_phase1_report(
    report_path: Path | str,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a markdown report summarising the baseline run."""
    lines = [
        "# Phase 1 — Baseline report",
        "",
        "## Source summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| API | {source_summary.get('api', '')} |",
        f"| Query | {source_summary.get('query', '')} |",
        f"| Filter | {source_summary.get('filter', '') or 'n/a'} |",
        f"| Rows ingested | {source_summary.get('rows', 0)} |",
        f"| Raw records file | `{source_summary.get('raw_records_path', '')}` |",
        f"| Clean dataset | `{source_summary.get('clean_csv', '')}` |",
        "",
        "## Evaluation metrics",
        "",
        *_metric_rows(metrics),
        "",
        "## Data quality",
        "",
        f"- **Status**: {'OK' if quality.get('ok') else 'FAILED'}",
        f"- Rows inspected: **{quality.get('row_count', 0)}**",
        f"- Duplicate paper_ids: **{quality.get('duplicate_paper_ids', 0)}**",
        f"- Missing titles: **{quality.get('missing_title', 0)}**",
        f"- Missing summaries: **{quality.get('missing_summary', 0)}**",
        f"- Short summaries: **{quality.get('short_summary_count', 0)}** (threshold {quality.get('short_summary_threshold', 50)} chars)",
        f"- Stale rows: **{quality.get('stale_rows', 0)}**",
        "",
    ]
    if quality.get("failures"):
        lines.append("> Quality failures detected:")
        for failure in quality["failures"]:
            lines.append(f"> - {failure}")
        lines.append("")

    lines.extend([
        "## Freshness",
        "",
        f"- Latest published: **{freshness.get('latest_published', '')}**",
        f"- Oldest published: **{freshness.get('oldest_published', '')}**",
        f"- Days since latest: **{freshness.get('days_since_latest', 'n/a')}**",
        f"- Stale rows: **{freshness.get('stale_rows', 0)}**",
        f"- Threshold: **{freshness.get('freshness_threshold_days', 'n/a')} days**",
        f"- Status: **{'FRESH' if freshness.get('is_fresh') else 'STALE'}**",
        "",
    ])
    write_text(Path(report_path), "\n".join(lines))


def _delta(baseline: float, other: float) -> str:
    if baseline is None or other is None:
        return "n/a"
    delta = other - baseline
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.4f}"


def generate_corruption_report(
    report_path: Path | str,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write a markdown report comparing baseline / corrupted / repaired."""
    comparison_rows = [
        "| Metric | Baseline | Corrupted | Δ (C − B) | Repaired | Δ (R − B) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for key in METRIC_KEYS:
        baseline_value = baseline_metrics.get(key)
        corrupted_value = corrupted_metrics.get(key)
        repaired_value = repaired_metrics.get(key)
        if isinstance(baseline_value, (int, float)) and isinstance(corrupted_value, (int, float)):
            delta_c = _delta(float(baseline_value), float(corrupted_value))
        else:
            delta_c = "n/a"
        if isinstance(baseline_value, (int, float)) and isinstance(repaired_value, (int, float)):
            delta_r = _delta(float(baseline_value), float(repaired_value))
        else:
            delta_r = "n/a"
        comparison_rows.append(
            f"| `{key}` | {_format_metric(baseline_value)} | {_format_metric(corrupted_value)} | {delta_c} | {_format_metric(repaired_value)} | {delta_r} |"
        )

    lines = [
        "# Corruption & Repair — Comparison report",
        "",
        "## Metric comparison (baseline ↔ corrupted ↔ repaired)",
        "",
        *comparison_rows,
        "",
        "## Data quality",
        "",
        "| State | Status | Rows | Duplicate IDs | Missing summary | Stale rows |",
        "| --- | --- | --- | --- | --- | --- |",
        f"| baseline | n/a | {baseline_metrics.get('samples', 'n/a')} | n/a | n/a | n/a |",
        f"| corrupted | {'OK' if corrupted_quality.get('ok') else 'FAILED'} | {corrupted_quality.get('row_count', 0)} | {corrupted_quality.get('duplicate_paper_ids', 0)} | {corrupted_quality.get('missing_summary', 0)} | {corrupted_quality.get('stale_rows', 0)} |",
        f"| repaired | {'OK' if repaired_quality.get('ok') else 'FAILED'} | {repaired_quality.get('row_count', 0)} | {repaired_quality.get('duplicate_paper_ids', 0)} | {repaired_quality.get('missing_summary', 0)} | {repaired_quality.get('stale_rows', 0)} |",
        "",
        "## Freshness",
        "",
        "| State | Latest | Days since latest | Stale rows | Is fresh |",
        "| --- | --- | --- | --- | --- |",
        f"| corrupted | {corrupted_freshness.get('latest_published', '')} | {corrupted_freshness.get('days_since_latest', 'n/a')} | {corrupted_freshness.get('stale_rows', 0)} | {'yes' if corrupted_freshness.get('is_fresh') else 'no'} |",
        f"| repaired | {repaired_freshness.get('latest_published', '')} | {repaired_freshness.get('days_since_latest', 'n/a')} | {repaired_freshness.get('stale_rows', 0)} | {'yes' if repaired_freshness.get('is_fresh') else 'no'} |",
        "",
        "## Narrative",
        "",
        "- The corrupted dataset intentionally drops recent rows, blanks summaries, injects noise,",
        "  truncates titles, shifts publication dates, and duplicates records.",
        "- A drop in `retrieval_hit_rate`, `judge_accuracy`, or `mean_judge_score` confirms",
        "  that the agent is sensitive to data quality issues.",
        "- The repaired dataset re-runs the cleaning pipeline from the raw snapshot; metrics",
        "  should recover close to the baseline.",
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))