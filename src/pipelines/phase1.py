from __future__ import annotations

import json

from core import (
    load_settings,
    now_utc,
    require_llm_credentials,
    write_csv,
    write_json,
)
from evaluation import build_test_set, evaluate_pipeline
from ingestion import build_clean_dataframe, fetch_source_records, load_raw_records
from observability import (
    build_freshness_report,
    generate_phase1_report,
    run_data_quality_checks,
)
from retrieval import LocalEmbeddingIndex

import logging
from pathlib import Path

import pandas as pd

from core.config import load_settings, normalized_provider, require_llm_credentials
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex


logger = logging.getLogger(__name__)
DEMO_QUESTIONS = [
    "What topics do the indexed papers cover?",
    "Find a paper about agentic retrieval augmented generation.",
    "List the most recent paper in the corpus.",
]


def _load_records(settings):
    raw_path = settings.paths.raw_records_json
    if settings.refresh_source or not raw_path.exists():
        logger.info("Fetching fresh records from %s", settings.source_api)
        return fetch_source_records(settings)
    logger.info("Reusing raw records snapshot at %s", raw_path)
    return load_raw_records(raw_path)


def _load_or_build_test_set(settings, df):
    eval_path = settings.paths.eval_testset
    if settings.refresh_test_set or not eval_path.exists():
        logger.info("Building evaluation set at %s", eval_path)
        return build_test_set(df, eval_path)
    logger.info("Reusing evaluation set at %s", eval_path)
    return read_json(eval_path)


def _try_run_demo_agent(settings, index) -> dict[str, object]:
    provider = normalized_provider(settings)
    try:
        require_llm_credentials(settings)
    except RuntimeError as exc:
        logger.warning("Skipping agent demo: %s", exc)
        return {"skipped": str(exc), "provider": provider}

    try:
        agent = build_agent(settings, index)
    except Exception as exc:  # pragma: no cover
        return {"skipped": f"agent build failed: {exc}", "provider": provider}

    answers: list[dict[str, str]] = []
    for question in DEMO_QUESTIONS:
        try:
            answer = run_agent_question(agent, question)
        except Exception as exc:  # pragma: no cover
            answer = f"agent error: {exc}"
        answers.append({"question": question, "answer": answer})
    return {"provider": provider, "answers": answers}


def main() -> None:
    """TODO(student): xay dung baseline pipeline end-to-end.

    Pseudo-code:
    1. Load settings.
    2. Load hoac fetch raw records.
    3. Clean data.
    4. Save clean CSV/JSON.
    5. Build Chroma index.
    6. Tao hoac load evaluation set.
    7. Evaluate.
    8. Run quality checks va freshness report.
    9. Tao markdown report.
    10. Co the demo agent tren vai sample question.
    """
    raise NotImplementedError("Student task: implement phase1 pipeline.")
