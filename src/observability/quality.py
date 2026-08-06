from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


SHORT_SUMMARY_THRESHOLD = 50


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