from __future__ import annotations

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
    """End-to-end baseline pipeline."""
    settings = load_settings()
    records = _load_records(settings)
    if not records:
        raise RuntimeError("No records returned from the source. Cannot build baseline.")

    df = build_clean_dataframe(records, now_utc())
    if df.empty:
        raise RuntimeError("Cleaned dataframe is empty after filtering. Check the raw snapshot.")

    write_csv(df, settings.paths.clean_csv)
    write_json(
        settings.paths.clean_json,
        df.to_dict(orient="records"),
    )

    index = LocalEmbeddingIndex.build(df, settings)

    test_set = _load_or_build_test_set(settings, df)
    if not test_set:
        raise RuntimeError("Evaluation set is empty. Cannot evaluate baseline.")

    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )

    quality = run_data_quality_checks(df, settings, "baseline_quality")
    freshness = build_freshness_report(df, settings, settings.paths.freshness_report)

    source_summary = {
        "api": settings.source_api,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": len(df),
        "raw_records_path": str(settings.paths.raw_records_json),
        "clean_csv": str(settings.paths.clean_csv),
    }
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=bundle.summary,
        quality=quality,
        freshness=freshness,
    )

    demo_payload = _try_run_demo_agent(settings, index)
    write_json(settings.paths.demo_answers, demo_payload)

    print("[phase1] rows=%s metrics=%s" % (len(df), bundle.summary))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()