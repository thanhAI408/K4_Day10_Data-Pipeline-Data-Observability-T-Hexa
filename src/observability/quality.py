from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


SHORT_SUMMARY_THRESHOLD = 50
from core.utils import write_json


def _non_empty_mask(df: pd.DataFrame, column: str) -> pd.Series:
    """Return a mask for values that are present and not blank."""
    if column not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)

    values = df[column].astype("string").fillna("").str.strip()
    return values.ne("")


def _numeric_column(df: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric column, coercing missing or invalid values to NaN."""
    if column not in df.columns:
        return pd.Series(float("nan"), index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def _published_column(df: pd.DataFrame) -> pd.Series:
    """Parse published dates while keeping invalid values as ``NaT``."""
    if "published" not in df.columns:
        return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")

    try:
        return pd.to_datetime(
            df["published"],
            errors="coerce",
            utc=True,
            format="mixed",
        )
    except TypeError:
        # ``format="mixed"`` is not supported by older pandas versions.
        return pd.to_datetime(df["published"], errors="coerce", utc=True)


def _freshness_metrics(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    """Calculate freshness values shared by both public report functions."""
    threshold_days = int(settings.freshness_threshold_days)
    total_rows = int(len(df))

    age_days = _numeric_column(df, "age_days")
    stale_mask = age_days.notna() & age_days.gt(threshold_days)
    stale_rows = int(stale_mask.sum())
    unknown_age_rows = int(age_days.isna().sum())

    published = _published_column(df)
    valid_published = published.dropna()
    if valid_published.empty:
        latest_published = None
        oldest_published = None
    else:
        latest_published = valid_published.max().date().isoformat()
        oldest_published = valid_published.min().date().isoformat()

    # A dataset with unknown age values cannot be declared fresh.  An empty
    # dataset is also not a fresh dataset, even though it has no stale rows.
    is_fresh = bool(total_rows > 0 and unknown_age_rows == 0 and stale_rows == 0)

    return {
        "latest_published": latest_published,
        "oldest_published": oldest_published,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "is_fresh": is_fresh,
        "unknown_age_rows": unknown_age_rows,
        "threshold_days": threshold_days,
    }


def _quality_report_path(settings: Settings, report_name: str) -> Path:
    """Resolve a quality report name below the configured quality directory."""
    name = str(report_name).strip()
    if not name:
        raise ValueError("report_name must not be empty")
    if not name.lower().endswith(".json"):
        name = f"{name}.json"
    return Path(settings.paths.quality_dir) / name


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run a fixed set of data quality checks and persist the report."""
    row_count = int(len(df))
    has_id = df["paper_id"].astype(str).str.len() > 0 if "paper_id" in df.columns else pd.Series([], dtype=bool)
    duplicate_paper_ids = (
        int(df["paper_id"].duplicated().sum()) if "paper_id" in df.columns else 0
    )
    missing_title = int((df["title"].astype(str).str.len() == 0).sum()) if "title" in df.columns else 0
    missing_summary = int((df["summary"].astype(str).str.len() == 0).sum()) if "summary" in df.columns else 0
    summary_lengths = (
        df["summary"].astype(str).str.len() if "summary" in df.columns else pd.Series([], dtype=int)
    )
    short_summary_count = int((summary_lengths < SHORT_SUMMARY_THRESHOLD).sum())
    age_series = pd.to_numeric(df.get("age_days"), errors="coerce").fillna(-1) if "age_days" in df.columns else pd.Series([], dtype=float)
    stale_rows = int((age_series > settings.freshness_threshold_days).sum())
    paper_id_unique = duplicate_paper_ids == 0

    failures: list[str] = []
    if row_count == 0:
        failures.append("row_count is zero")
    if not paper_id_unique:
        failures.append(f"{duplicate_paper_ids} duplicate paper_id values")
    if missing_title:
        failures.append(f"{missing_title} rows missing title")
    if missing_summary:
        failures.append(f"{missing_summary} rows missing summary")
    if short_summary_count:
        failures.append(f"{short_summary_count} rows have summary shorter than {SHORT_SUMMARY_THRESHOLD} chars")
    if stale_rows:
        failures.append(f"{stale_rows} rows exceed the freshness threshold of {settings.freshness_threshold_days} days")

    report = {
        "report_name": report_name,
        "row_count": row_count,
        "paper_id_unique": bool(paper_id_unique),
        "duplicate_paper_ids": duplicate_paper_ids,
        "missing_title": missing_title,
        "missing_summary": missing_summary,
        "short_summary_count": short_summary_count,
        "stale_rows": stale_rows,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "ok": not failures,
        "failures": failures,
        "generated_at": datetime.now(UTC).isoformat(),
    }

    output_path = settings.paths.quality_dir / f"{report_name}.json"
    write_json(Path(output_path), report)
    return report
    """Run data quality checks and persist the resulting JSON report.

    The report contains per-check pass/fail values and counts so that
    baseline, corrupted, and repaired datasets can be compared.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")

    total_rows = int(len(df))
    required_columns = ["paper_id", "title", "summary", "age_days"]
    missing_columns = [column for column in required_columns if column not in df.columns]

    paper_id_present = "paper_id" in df.columns
    valid_paper_ids = _non_empty_mask(df, "paper_id")
    missing_paper_id_rows = int((~valid_paper_ids).sum())

    duplicate_paper_id_rows = 0
    duplicate_paper_id_values = 0
    if paper_id_present:
        paper_ids = df.loc[valid_paper_ids, "paper_id"].astype("string").str.strip()
        duplicate_mask = paper_ids.duplicated(keep="first")
        duplicate_paper_id_rows = int(duplicate_mask.sum())
        duplicate_paper_id_values = int(
            paper_ids[paper_ids.duplicated(keep=False)].nunique()
        )

    title_present = "title" in df.columns
    valid_titles = _non_empty_mask(df, "title")
    missing_title_rows = int((~valid_titles).sum())

    summary_present = "summary" in df.columns
    if summary_present:
        summary_values = df["summary"].astype("string").fillna("").str.strip()
        summary_lengths = summary_values.str.len()
        empty_summary_rows = int(summary_lengths.eq(0).sum())
        min_summary_chars = (
            int(summary_lengths.min()) if not summary_lengths.empty else None
        )
        max_summary_chars = (
            int(summary_lengths.max()) if not summary_lengths.empty else None
        )
        average_summary_chars = (
            float(summary_lengths.mean()) if not summary_lengths.empty else None
        )
    else:
        empty_summary_rows = total_rows
        min_summary_chars = None
        max_summary_chars = None
        average_summary_chars = None

    freshness = _freshness_metrics(df, settings)

    checks: dict[str, Any] = {
        "row_count": {
            "passed": bool(total_rows > 0),
            "value": total_rows,
            "minimum_expected": 1,
        },
        "paper_id_not_null": {
            "passed": bool(paper_id_present and missing_paper_id_rows == 0),
            "missing_rows": missing_paper_id_rows,
        },
        "paper_id_unique": {
            "passed": bool(paper_id_present and duplicate_paper_id_rows == 0),
            "duplicate_rows": duplicate_paper_id_rows,
            "duplicate_values": duplicate_paper_id_values,
        },
        "title_not_null": {
            "passed": bool(title_present and missing_title_rows == 0),
            "missing_rows": missing_title_rows,
        },
        "summary_length": {
            "passed": bool(summary_present and empty_summary_rows == 0),
            "empty_rows": empty_summary_rows,
            "minimum_required_chars": 1,
            "min_chars": min_summary_chars,
            "max_chars": max_summary_chars,
            "average_chars": average_summary_chars,
        },
        "freshness": {
            "passed": freshness["is_fresh"],
            "stale_rows": freshness["stale_rows"],
            "unknown_age_rows": freshness["unknown_age_rows"],
            "threshold_days": freshness["threshold_days"],
        },
    }

    passed = bool(all(check["passed"] for check in checks.values()))
    report = {
        "report_name": str(report_name),
        "total_rows": total_rows,
        "missing_columns": missing_columns,
        "passed": passed,
        "status": "pass" if passed else "fail",
        "checks": checks,
    }

    write_json(_quality_report_path(settings, report_name), report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path: Path | str) -> dict[str, Any]:
    """Summarize corpus freshness into a JSON payload."""
    if df.empty or "published" not in df.columns:
        report = {
            "total_rows": 0,
            "latest_published": "",
            "oldest_published": "",
            "stale_rows": 0,
            "freshness_threshold_days": settings.freshness_threshold_days,
            "is_fresh": False,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        write_json(Path(report_path), report)
        return report

    parsed = pd.to_datetime(df["published"], errors="coerce")
    valid = parsed.dropna()
    latest = valid.max() if not valid.empty else None
    oldest = valid.min() if not valid.empty else None
    age_series = pd.to_numeric(df.get("age_days"), errors="coerce").fillna(-1)
    stale_rows = int((age_series > settings.freshness_threshold_days).sum())

    latest_iso = latest.date().isoformat() if latest is not None else ""
    oldest_iso = oldest.date().isoformat() if oldest is not None else ""
    days_since_latest = (
        (datetime.now(UTC).date() - latest.date()).days if latest is not None else None
    )
    is_fresh = (
        latest is not None
        and stale_rows == 0
        and days_since_latest is not None
        and days_since_latest <= settings.freshness_threshold_days
    )

    report = {
        "total_rows": int(len(df)),
        "latest_published": latest_iso,
        "oldest_published": oldest_iso,
        "stale_rows": stale_rows,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "days_since_latest": days_since_latest,
        "is_fresh": bool(is_fresh),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    write_json(Path(report_path), report)
    return report
def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Build and persist a report describing dataset freshness.

    Rows are considered stale when ``age_days`` is greater than the
    configured freshness threshold.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")

    metrics = _freshness_metrics(df, settings)
    report = {
        "latest_published": metrics["latest_published"],
        "oldest_published": metrics["oldest_published"],
        "stale_rows": metrics["stale_rows"],
        "total_rows": metrics["total_rows"],
        "is_fresh": metrics["is_fresh"],
    }

    write_json(Path(report_path), report)
    return report
