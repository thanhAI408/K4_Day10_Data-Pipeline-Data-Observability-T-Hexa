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


def main() -> None:
    """Run the clean-data baseline pipeline end-to-end."""

    # 1. Load project settings and validate the selected LLM provider.
    settings = load_settings()
    require_llm_credentials(settings)

    print("[1/9] Loading raw Crossref records...")

    # Reuse the saved raw snapshot unless REFRESH_SOURCE=true.
    if settings.paths.raw_records_json.exists() and not settings.refresh_source:
        records = load_raw_records(settings.paths.raw_records_json)
        source_mode = "loaded_from_snapshot"
    else:
        records = fetch_source_records(settings)
        source_mode = "fetched_from_crossref"

    if not records:
        raise RuntimeError("No raw records were available for the baseline pipeline.")

    print(f"      Raw records: {len(records)}")

    # 2. Clean and model the records.
    print("[2/9] Cleaning records...")
    run_date = now_utc()
    clean_df = build_clean_dataframe(records, run_date=run_date)

    if clean_df.empty:
        raise RuntimeError("Cleaning produced an empty dataframe.")

    if "paper_id" not in clean_df.columns:
        raise RuntimeError("Clean dataframe is missing required column: paper_id.")

    if "text_for_embedding" not in clean_df.columns:
        raise RuntimeError(
            "Clean dataframe is missing required column: text_for_embedding."
        )

    print(f"      Clean records: {len(clean_df)}")

    # 3. Save clean CSV and JSON artifacts.
    print("[3/9] Saving clean artifacts...")
    write_csv(clean_df, settings.paths.clean_csv)

    # Convert through pandas JSON so Timestamp and other pandas values
    # become JSON-serializable values.
    clean_records = json.loads(
        clean_df.to_json(
            orient="records",
            date_format="iso",
            force_ascii=False,
        )
    )
    write_json(settings.paths.clean_json, clean_records)

    # 4. Build the baseline ChromaDB index.
    print("[4/9] Building baseline embedding index...")
    index = LocalEmbeddingIndex.build(
        df=clean_df,
        settings=settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )

    # 5. Create or reuse a fixed evaluation set.
    print("[5/9] Preparing evaluation test set...")
    if settings.paths.eval_testset.exists() and not settings.refresh_test_set:
        test_set_mode = "reused_existing_test_set"
    else:
        build_test_set(clean_df, settings.paths.eval_testset)
        test_set_mode = "created_new_test_set"

    if not settings.paths.eval_testset.exists():
        raise RuntimeError("Evaluation test set was not created.")

    # 6. Evaluate retrieval and answers.
    print("[6/9] Evaluating baseline pipeline...")
    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )

    # 7. Run data quality checks.
    print("[7/9] Running data quality checks...")
    quality = run_data_quality_checks(
        df=clean_df,
        settings=settings,
        report_name="baseline",
    )

    # 8. Build freshness report.
    print("[8/9] Building freshness report...")
    freshness = build_freshness_report(
        df=clean_df,
        settings=settings,
        report_path=settings.paths.freshness_report,
    )

    # 9. Generate the Markdown baseline report.
    print("[9/9] Generating baseline report...")
    source_summary = {
        "source": settings.source_api,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "source_mode": source_mode,
        "raw_record_count": len(records),
        "clean_record_count": len(clean_df),
        "test_set_mode": test_set_mode,
        "embedding_model": settings.embedding_model,
        "collection_name": index.collection_name,
        "top_k": settings.top_k,
        "run_date_utc": run_date.isoformat(),
    }

    generate_phase1_report(
        report_path=settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )

    print()
    print("Baseline pipeline completed successfully.")
    print(f"Metrics: {settings.paths.baseline_metrics}")
    print(f"Answers: {settings.paths.baseline_answers}")
    print(f"Report:  {settings.paths.baseline_report}")


if __name__ == "__main__":
    main()