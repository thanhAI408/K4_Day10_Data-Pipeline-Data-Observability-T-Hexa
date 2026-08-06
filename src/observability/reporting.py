from __future__ import annotations

import json
import math
from numbers import Real
from pathlib import Path
from typing import Any

from core.utils import write_text


_EVALUATION_METRICS = (
    "retrieval_hit_rate",
    "mean_token_f1",
    "judge_accuracy",
    "mean_judge_score",
    "ragas",
)


def _format_value(value: Any) -> str:
    """Format a value for a compact Markdown table cell."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Real):
        numeric = float(value)
        if not math.isfinite(numeric):
            return "N/A"
        formatted = f"{numeric:.4f}".rstrip("0").rstrip(".")
        return formatted or "0"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def _cell(value: Any) -> str:
    """Escape a value so it can safely be used in a Markdown table."""
    return _format_value(value).replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def _markdown_table(headers: list[str], rows: list[tuple[Any, ...]]) -> str:
    """Render rows as a GitHub-compatible Markdown table."""
    header_line = "| " + " | ".join(_cell(header) for header in headers) + " |"
    separator_line = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(_cell(value) for value in row) + " |"
        for row in rows
    ]
    return "\n".join([header_line, separator_line, *body])


def _metric_value(metrics: dict[str, Any], name: str) -> Any:
    """Read a metric from either a flat summary or a nested summary."""
    if not isinstance(metrics, dict):
        return None
    if name in metrics:
        return metrics[name]

    for nested_name in ("summary", "metrics"):
        nested = metrics.get(nested_name)
        if isinstance(nested, dict) and name in nested:
            return nested[name]
    return None


def _numeric_metric(metrics: dict[str, Any], name: str) -> float | None:
    """Return a finite numeric metric, excluding booleans and structures."""
    value = _metric_value(metrics, name)
    if isinstance(value, bool) or isinstance(value, (dict, list, tuple)):
        return None
    if isinstance(value, Real):
        numeric = float(value)
    elif isinstance(value, str):
        try:
            numeric = float(value)
        except ValueError:
            return None
    else:
        return None
    return numeric if math.isfinite(numeric) else None


def _metric_delta(left: dict[str, Any], right: dict[str, Any], name: str) -> float | None:
    """Calculate ``right - left`` for a numeric metric."""
    left_value = _numeric_metric(left, name)
    right_value = _numeric_metric(right, name)
    if left_value is None or right_value is None:
        return None
    return right_value - left_value


def _result_label(value: Any) -> str:
    """Normalize pass/fail-like values for report output."""
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if value is None:
        return "UNKNOWN"
    normalized = str(value).strip().lower()
    if normalized in {"pass", "passed", "success", "fresh", "true", "ok"}:
        return "PASS"
    if normalized in {"fail", "failed", "failure", "stale", "false", "error"}:
        return "FAIL"
    return str(value)


def _quality_status(quality: dict[str, Any]) -> str:
    """Get the overall status from a quality report."""
    if not isinstance(quality, dict):
        return "UNKNOWN"
    if "passed" in quality:
        return _result_label(quality["passed"])
    if "status" in quality:
        return _result_label(quality["status"])

    checks = quality.get("checks")
    if isinstance(checks, dict) and checks:
        statuses = [
            check.get("passed")
            for check in checks.values()
            if isinstance(check, dict) and "passed" in check
        ]
        if statuses and all(value is True for value in statuses):
            return "PASS"
        if statuses and any(value is False for value in statuses):
            return "FAIL"
    return "UNKNOWN"


def _freshness_status(freshness: dict[str, Any]) -> str:
    """Get a human-readable freshness status from a freshness report."""
    if not isinstance(freshness, dict):
        return "UNKNOWN"
    if "is_fresh" in freshness:
        return "FRESH" if freshness["is_fresh"] is True else "STALE"

    stale_rows = freshness.get("stale_rows")
    total_rows = freshness.get("total_rows")
    if isinstance(stale_rows, Real) and isinstance(total_rows, Real) and total_rows > 0:
        return "FRESH" if stale_rows == 0 else "STALE"
    return "UNKNOWN"


def _quality_check_rows(quality: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Convert a quality payload into rows for a Markdown table."""
    if not isinstance(quality, dict):
        return [("overall", "UNKNOWN", "No quality report supplied")]

    checks = quality.get("checks")
    if not isinstance(checks, dict) or not checks:
        return [("overall", _quality_status(quality), "No per-check details supplied")]

    rows: list[tuple[str, str, str]] = []
    for name, check in checks.items():
        if isinstance(check, dict):
            result = _result_label(check.get("passed"))
            details = "; ".join(
                f"{key}={_format_value(value)}"
                for key, value in check.items()
                if key != "passed"
            )
        else:
            result = _result_label(check)
            details = ""
        rows.append((f"`{name}`", result, details or "-"))
    return rows


def _quality_threshold(quality: dict[str, Any]) -> Any:
    """Read the freshness threshold when it is present in a quality report."""
    if not isinstance(quality, dict):
        return None
    checks = quality.get("checks")
    if isinstance(checks, dict):
        freshness = checks.get("freshness")
        if isinstance(freshness, dict):
            return freshness.get("threshold_days")
    return quality.get("threshold_days")


def _freshness_field(freshness: dict[str, Any], name: str) -> Any:
    if isinstance(freshness, dict):
        return freshness.get(name)
    return None


def _source_rows(source_summary: dict[str, Any]) -> list[tuple[str, Any]]:
    """Keep source fields readable and deterministic in the report."""
    if not isinstance(source_summary, dict) or not source_summary:
        return [("source_summary", "N/A")]

    preferred = (
        "source_api",
        "source",
        "source_query",
        "query",
        "source_filter",
        "filter",
        "record_count",
        "records",
        "fetched_at",
    )
    ordered_keys = [key for key in preferred if key in source_summary]
    ordered_keys.extend(key for key in source_summary if key not in ordered_keys)
    return [(f"`{key}`", source_summary[key]) for key in ordered_keys]


def _write_report(report_path: Any, sections: list[str]) -> None:
    content = "\n\n".join(section.strip() for section in sections if section.strip())
    write_text(Path(report_path), content.rstrip() + "\n")


def _state_recovery(baseline: str, corrupted: str, repaired: str) -> str:
    if repaired == baseline:
        return "recovered to baseline"
    if repaired == corrupted:
        return "not recovered"
    return f"partial: {corrupted} -> {repaired}"


def _metric_note(
    baseline: dict[str, Any],
    corrupted: dict[str, Any],
    repaired: dict[str, Any],
    name: str,
) -> str:
    baseline_value = _numeric_metric(baseline, name)
    corrupted_value = _numeric_metric(corrupted, name)
    repaired_value = _numeric_metric(repaired, name)
    if baseline_value is None or corrupted_value is None or repaired_value is None:
        return "non-numeric or unavailable"
    if math.isclose(corrupted_value, baseline_value) and math.isclose(repaired_value, baseline_value):
        return "unchanged across the three states"
    if math.isclose(repaired_value, baseline_value):
        return "repair returned to baseline"
    if math.isclose(repaired_value, corrupted_value):
        return "repair did not change the metric"
    return "repair produced a partial or different recovery"


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a Markdown report for the baseline pipeline.

    The function intentionally renders the supplied payloads rather than
    inventing results, so the report remains traceable to pipeline artifacts.
    """
    source_rows = _source_rows(source_summary)
    metric_rows = [
        (f"`{name}`", _metric_value(metrics, name))
        for name in _EVALUATION_METRICS
    ]
    quality_rows = _quality_check_rows(quality)
    freshness_rows = [
        ("latest_published", _freshness_field(freshness, "latest_published")),
        ("oldest_published", _freshness_field(freshness, "oldest_published")),
        ("stale_rows", _freshness_field(freshness, "stale_rows")),
        ("total_rows", _freshness_field(freshness, "total_rows")),
        ("status", _freshness_status(freshness)),
        ("is_fresh", _freshness_field(freshness, "is_fresh")),
        ("threshold_days", _quality_threshold(quality)),
    ]

    sections = [
        "# Phase 1 Baseline Report",
        "## Source summary\n" + _markdown_table(["Field", "Value"], source_rows),
        "## Evaluation metrics\n" + _markdown_table(["Metric", "Value"], metric_rows),
        (
            "## Data quality\n"
            + _markdown_table(["Check", "Result", "Details"], quality_rows)
            + f"\n\nOverall quality status: **{_quality_status(quality)}**"
        ),
        "## Freshness\n" + _markdown_table(["Field", "Value"], freshness_rows),
    ]
    _write_report(report_path, sections)


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write a Markdown comparison of baseline, corrupted, and repaired runs.

    The current function contract supplies baseline metrics but only
    corrupted/repaired quality and freshness payloads; the report marks the
    unavailable baseline observability values as ``N/A``.
    """
    metric_rows: list[tuple[Any, ...]] = []
    for name in _EVALUATION_METRICS:
        metric_rows.append(
            (
                f"`{name}`",
                _metric_value(baseline_metrics, name),
                _metric_value(corrupted_metrics, name),
                _metric_value(repaired_metrics, name),
                _metric_delta(baseline_metrics, corrupted_metrics, name),
                _metric_delta(corrupted_metrics, repaired_metrics, name),
                _metric_note(baseline_metrics, corrupted_metrics, repaired_metrics, name),
            )
        )

    corrupted_quality_label = _quality_status(corrupted_quality)
    repaired_quality_label = _quality_status(repaired_quality)

    corrupted_freshness_label = _freshness_status(corrupted_freshness)
    repaired_freshness_label = _freshness_status(repaired_freshness)

    freshness_detail_rows = [
        (
            name,
            _freshness_field(corrupted_freshness, name),
            _freshness_field(repaired_freshness, name),
        )
        for name in (
            "latest_published",
            "oldest_published",
            "stale_rows",
            "total_rows",
            "is_fresh",
        )
    ]

    quality_rows = [
        (
            "Quality checks pass/fail",
            "N/A",
            corrupted_quality_label,
            repaired_quality_label,
            "N/A (baseline quality was not supplied)",
            _state_recovery("N/A", corrupted_quality_label, repaired_quality_label),
            "Baseline quality is not an argument of this function",
        ),
        (
            "Freshness status",
            "N/A",
            corrupted_freshness_label,
            repaired_freshness_label,
            "N/A (baseline freshness was not supplied)",
            _state_recovery("N/A", corrupted_freshness_label, repaired_freshness_label),
            "Baseline freshness is not an argument of this function",
        ),
    ]

    sections = [
        "# Corruption Comparison Report",
        (
            "## Evaluation metric comparison\n"
            + _markdown_table(
                [
                    "Metric",
                    "Baseline",
                    "Corrupted",
                    "Repaired",
                    "Change: corrupted - baseline",
                    "Recovery: repaired - corrupted",
                    "Note",
                ],
                metric_rows,
            )
        ),
        (
            "## Quality and freshness comparison\n"
            + _markdown_table(
                [
                    "Signal",
                    "Baseline",
                    "Corrupted",
                    "Repaired",
                    "Change due to corruption",
                    "Recovery",
                    "Note",
                ],
                quality_rows,
            )
        ),
        (
            "## Quality check details\n"
            "### Corrupted\n"
            + _markdown_table(
                ["Check", "Result", "Details"],
                _quality_check_rows(corrupted_quality),
            )
            + "\n\n### Repaired\n"
            + _markdown_table(
                ["Check", "Result", "Details"],
                _quality_check_rows(repaired_quality),
            )
        ),
        (
            "## Freshness details\n"
            + _markdown_table(
                ["Field", "Corrupted", "Repaired"],
                freshness_detail_rows,
            )
        ),
        "## Observations\n" + _comparison_observations(
            baseline_metrics,
            corrupted_metrics,
            repaired_metrics,
            corrupted_quality,
            repaired_quality,
            corrupted_freshness,
            repaired_freshness,
        ),
    ]
    _write_report(report_path, sections)


def _comparison_observations(
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> str:
    """Summarize observed changes without asserting unsupported causality."""
    observations: list[str] = []
    for name in _EVALUATION_METRICS[:-1]:
        baseline_value = _numeric_metric(baseline_metrics, name)
        corrupted_value = _numeric_metric(corrupted_metrics, name)
        repaired_value = _numeric_metric(repaired_metrics, name)
        if baseline_value is None or corrupted_value is None or repaired_value is None:
            continue
        if not math.isclose(baseline_value, corrupted_value):
            observations.append(
                f"`{name}` changed from {_format_value(baseline_value)} in baseline "
                f"to {_format_value(corrupted_value)} after corruption; repaired is "
                f"{_format_value(repaired_value)}."
            )

    corrupted_quality_label = _quality_status(corrupted_quality)
    repaired_quality_label = _quality_status(repaired_quality)
    if corrupted_quality_label != repaired_quality_label:
        observations.append(
            f"Quality status changed from **{corrupted_quality_label}** in the "
            f"corrupted dataset to **{repaired_quality_label}** after repair."
        )

    corrupted_freshness_label = _freshness_status(corrupted_freshness)
    repaired_freshness_label = _freshness_status(repaired_freshness)
    if corrupted_freshness_label != repaired_freshness_label:
        observations.append(
            f"Freshness status changed from **{corrupted_freshness_label}** in the "
            f"corrupted dataset to **{repaired_freshness_label}** after repair."
        )

    if not observations:
        observations.append("No measurable change was found in the supplied comparison payloads.")
    return "\n".join(f"- {observation}" for observation in observations)
