from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Iterable

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord


CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "age_days",
    "text_for_embedding",
]


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_text_for_embedding(row: pd.Series) -> str:
    parts = [row["title"]]
    if row["summary"]:
        parts.append(row["summary"])
    if row["authors_joined"]:
        parts.append(f"Authors: {row['authors_joined']}")
    if row["categories_joined"]:
        parts.append(f"Categories: {row['categories_joined']}")
    if row["published"]:
        parts.append(f"Published: {row['published']}")
    return ". ".join(parts) + "."


def _records_to_dataframe(records: Iterable[PaperRecord]) -> pd.DataFrame:
    rows = [asdict(record) for record in records]
    if not rows:
        return pd.DataFrame(columns=CLEAN_COLUMNS)
    df = pd.DataFrame(rows)
    df["title"] = df["title"].astype(str).map(normalize_whitespace)
    df["summary"] = df["summary"].astype(str).map(normalize_whitespace)
    df["comment"] = df["comment"].astype(str).map(normalize_whitespace)
    df["authors_joined"] = df["authors"].apply(lambda values: compact_join(values or []))
    df["categories_joined"] = df["categories"].apply(lambda values: compact_join(values or []))
    df["summary_chars"] = df["summary"].str.len().fillna(0).astype(int)
    return df


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Normalize raw records into a tidy dataframe ready for embedding."""
    df = _records_to_dataframe(records)
    if df.empty:
        return pd.DataFrame(columns=CLEAN_COLUMNS)

    df = df.dropna(subset=["paper_id", "title"])
    df = df[df["title"].str.len() > 0]
    df = df.drop_duplicates(subset=["paper_id"], keep="first")

    parsed_published = df["published"].apply(_parse_iso_date)
    parsed_updated = df["updated"].apply(_parse_iso_date)
    df["published"] = parsed_published.apply(lambda dt: dt.date().isoformat() if dt else "")
    df["updated"] = parsed_updated.apply(lambda dt: dt.date().isoformat() if dt else "")

    def _days_since(target: datetime | None) -> int:
        if target is None:
            return -1
        # Strip tz info to match `datetime.fromisoformat` which is naive.
        run_naive = run_date.replace(tzinfo=None) if run_date.tzinfo else run_date
        return max((run_naive - target).days, 0)

    age_from_published = parsed_published.apply(_days_since)
    age_from_updated = parsed_updated.apply(_days_since)
    df["age_days"] = age_from_published.where(age_from_published >= 0, age_from_updated)
    df["age_days"] = df["age_days"].fillna(-1).astype(int)

    df["text_for_embedding"] = df.apply(_format_text_for_embedding, axis=1)
    df = df.sort_values(by=["published", "title"], ascending=[False, True]).reset_index(drop=True)
    return df[CLEAN_COLUMNS]