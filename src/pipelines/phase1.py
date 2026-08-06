from __future__ import annotations

from typing import Any

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation import build_test_set, evaluate_pipeline
from ingestion import build_clean_dataframe, fetch_source_records, load_raw_records
from observability import build_freshness_report, generate_phase1_report, run_data_quality_checks
from retrieval import LocalEmbeddingIndex, build_agent, run_agent_question


def _load_or_fetch_records(settings: Settings) -> list:
    raw_path = settings.paths.raw_records_json
    if settings.refresh_source or not raw_path.exists():
        print(f"[phase1] Fetching raw records from {settings.source_api} ...")
        records = fetch_source_records(settings)
    else:
        print(f"[phase1] Loading cached raw records from {raw_path} ...")
        records = load_raw_records(raw_path)
    print(f"[phase1] {len(records)} raw records available.")
    return records


def _load_or_build_test_set(settings: Settings, df) -> list[dict[str, Any]]:
    test_set_path = settings.paths.eval_testset
    if settings.refresh_test_set or not test_set_path.exists():
        print("[phase1] Building evaluation test set ...")
        test_set = build_test_set(df, test_set_path)
    else:
        print(f"[phase1] Loading cached evaluation test set from {test_set_path} ...")
        test_set = read_json(test_set_path)
    print(f"[phase1] Evaluation test set has {len(test_set)} questions.")
    return test_set


def _demo_agent(settings: Settings, index: LocalEmbeddingIndex, test_set: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Optional demo: run a few sample questions through the conversational agent."""
    demo_samples = test_set[:3]
    if not demo_samples:
        return []

    try:
        agent = build_agent(settings, index)
    except Exception as exc:  # pragma: no cover - depends on LLM credentials
        print(f"[phase1] Skipping agent demo (agent could not be built): {exc}")
        return []

    demo_answers: list[dict[str, Any]] = []
    for sample in demo_samples:
        question = sample["question"]
        try:
            answer = run_agent_question(agent, question)
        except Exception as exc:  # pragma: no cover - depends on LLM credentials
            answer = f"Agent demo failed: {exc}"
        demo_answers.append({"question": question, "answer": answer})
        print(f"[phase1] Agent demo Q: {question}")
        print(f"[phase1] Agent demo A: {answer}")
    return demo_answers


def main() -> None:
    """Baseline pipeline end-to-end: ingest -> clean -> index -> evaluate -> observe -> report."""
    settings = load_settings()
    run_date = now_utc()

    # 1-2. Load or fetch raw records.
    records = _load_or_fetch_records(settings)

    # 3-4. Clean data and persist clean CSV/JSON.
    print("[phase1] Cleaning raw records ...")
    df = build_clean_dataframe(records, run_date=run_date)
    print(f"[phase1] Clean dataset has {len(df)} rows.")

    write_csv(df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, df.to_dict(orient="records"))

    # 5. Build the Chroma embedding index.
    print("[phase1] Building embedding index in ChromaDB ...")
    index = LocalEmbeddingIndex.build(df, settings, embeddings_output_path=settings.paths.embeddings_json)

    # 6. Create or load the evaluation test set.
    test_set = _load_or_build_test_set(settings, df)

    # 7. Evaluate the baseline pipeline.
    print("[phase1] Evaluating baseline pipeline ...")
    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    print(
        "[phase1] Baseline metrics: "
        f"retrieval_hit_rate={bundle.summary['retrieval_hit_rate']:.3f}, "
        f"mean_token_f1={bundle.summary['mean_token_f1']:.3f}, "
        f"judge_accuracy={bundle.summary['judge_accuracy']:.3f}, "
        f"mean_judge_score={bundle.summary['mean_judge_score']:.3f}"
    )

    # 8. Run data quality checks and freshness report.
    print("[phase1] Running data quality checks ...")
    quality = run_data_quality_checks(df, settings, report_name="baseline")

    print("[phase1] Building freshness report ...")
    freshness = build_freshness_report(df, settings, settings.paths.freshness_report)

    # 10. Optional agent demo on a few sample questions.
    demo_answers = _demo_agent(settings, index, test_set)
    if demo_answers:
        write_json(settings.paths.demo_answers, demo_answers)

    # 9. Generate the markdown report.
    source_summary = {
        "source_api": settings.source_api,
        "source_query": settings.source_query,
        "source_filter": settings.source_filter,
        "max_results": settings.max_results,
        "records_fetched": len(records),
        "records_after_cleaning": len(df),
        "run_date": run_date.isoformat(),
    }

    print("[phase1] Generating phase 1 markdown report ...")
    generate_phase1_report(
        report_path=settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=bundle.summary,
        quality=quality,
        freshness=freshness,
    )

    print(f"[phase1] Done. Report written to {settings.paths.baseline_report}")