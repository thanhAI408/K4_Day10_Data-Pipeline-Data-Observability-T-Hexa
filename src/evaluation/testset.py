from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import write_json


MIN_DOCUMENTS = 5
MAX_DOCUMENTS = 6


def _question_for(question_type: str, title: str) -> str:
    if question_type == "summary":
        return f"Summarize the paper titled '{title}'."
    if question_type == "authors":
        return f"Who authored '{title}'?"
    if question_type == "date":
        return f"When was '{title}' published?"
    if question_type == "categories":
        return f"What categories does '{title}' belong to?"
    raise ValueError(f"Unsupported question_type: {question_type}")


def _ground_truth(row: pd.Series, question_type: str) -> str:
    if question_type == "summary":
        return str(row.get("summary") or "").strip()
    if question_type == "authors":
        return str(row.get("authors_joined") or "").strip()
    if question_type == "date":
        return str(row.get("published") or "").strip()
    if question_type == "categories":
        return str(row.get("categories_joined") or row.get("primary_category") or "").strip()
    return ""


def build_test_set(df: pd.DataFrame, output_path: Path | str, max_docs: int = MAX_DOCUMENTS) -> list[dict[str, Any]]:
    """Create an evaluation set of factual questions derived from the cleaned corpus."""
    if df.empty or len(df) < MIN_DOCUMENTS:
        raise ValueError(
            f"Need at least {MIN_DOCUMENTS} cleaned documents to build the test set, got {len(df)}."
        )

    candidates = df.head(max_docs).reset_index(drop=True)
    question_types = ["summary", "authors", "date", "categories"]
    items: list[dict[str, Any]] = []
    counter = 0
    for _, row in candidates.iterrows():
        title = str(row.get("title") or "").strip()
        paper_id = str(row.get("paper_id") or "").strip()
        if not title or not paper_id:
            continue
        for question_type in question_types:
            counter += 1
            ground_truth = _ground_truth(row, question_type)
            if question_type in {"summary", "authors", "categories"} and not ground_truth:
                continue
            items.append(
                {
                    "id": f"q{counter:03d}",
                    "question_type": question_type,
                    "question": _question_for(question_type, title),
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": [paper_id],
                }
            )

    if not items:
        raise ValueError("Test set is empty after filtering — check the cleaned corpus.")

    write_json(Path(output_path), items)
    return items