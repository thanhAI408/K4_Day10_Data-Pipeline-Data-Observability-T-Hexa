from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation import evaluate_pipeline
from ingestion import build_clean_dataframe, corrupt_clean_dataframe, load_raw_records
from observability import build_freshness_report, generate_corruption_report, run_data_quality_checks
from retrieval import LocalEmbeddingIndex


def _require_baseline_artifacts(settings: Settings) -> None:
    required = (
        settings.paths.clean_json,
        settings.paths.baseline_metrics,
        settings.paths.eval_testset,
        settings.paths.raw_records_json,
    )
    missing = [path for path in required if not Path(path).exists()]
    if missing:
        missing_list = ", ".join(str(path) for path in missing)
        raise RuntimeError(
            "Missing baseline artifacts required before running the corruption flow: "
            f"{missing_list}. Run `python script/run_phase1.py` first."
        )


def _load_clean_dataframe(path: Path) -> pd.DataFrame:
    records = read_json(path)
    return pd.DataFrame(records)


def _print_metrics(label: str, metrics: dict[str, Any]) -> None:
    print(
        f"[corruption_flow] {label} metrics: "
        f"retrieval_hit_rate={metrics.get('retrieval_hit_rate', 0):.3f}, "
        f"mean_token_f1={metrics.get('mean_token_f1', 0):.3f}, "
        f"judge_accuracy={metrics.get('judge_accuracy', 0):.3f}, "
        f"mean_judge_score={metrics.get('mean_judge_score', 0):.3f}"
    )


def main() -> None:
    """Corruption -> evaluate -> repair -> compare flow (runs after phase1)."""
    settings = load_settings()
    _require_baseline_artifacts(settings)

    # 1. Load baseline metrics and clean dataset.
    baseline_metrics = read_json(settings.paths.baseline_metrics)
    baseline_df = _load_clean_dataframe(settings.paths.clean_json)
    print(f"[corruption_flow] Loaded baseline dataset with {len(baseline_df)} rows.")

    # 2-3. Build and persist the corrupted dataframe (corruption log written internally).
    print("[corruption_flow] Corrupting clean dataset ...")
    corrupted_df = corrupt_clean_dataframe(baseline_df.copy(deep=True), settings.paths.corruption_log)
    print(f"[corruption_flow] Corrupted dataset has {len(corrupted_df)} rows.")

    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, corrupted_df.to_dict(orient="records"))

    # 4. Rebuild index and evaluate on the corrupted dataset.
    print("[corruption_flow] Rebuilding embedding index on corrupted data ...")
    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df, settings, embeddings_output_path=settings.paths.corrupted_embeddings_json
    )

    print("[corruption_flow] Evaluating corrupted dataset ...")
    corrupted_bundle = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.corrupted_metrics,
        answers_output_path=settings.paths.corrupted_answers,
    )
    _print_metrics("Corrupted", corrupted_bundle.summary)

    # 5. Run quality checks/freshness on the corrupted data.
    print("[corruption_flow] Running data quality checks on corrupted data ...")
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, report_name="corrupted")

    print("[corruption_flow] Building freshness report on corrupted data ...")
    corrupted_freshness_path = settings.paths.quality_dir / "freshness_report_corrupted.json"
    corrupted_freshness = build_freshness_report(corrupted_df, settings, corrupted_freshness_path)

    # 6. Repair from the original raw records (independent of the corrupted dataframe).
    print("[corruption_flow] Repairing dataset from raw source ...")
    raw_records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(raw_records, run_date=now_utc())
    print(f"[corruption_flow] Repaired dataset has {len(repaired_df)} rows.")

    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, repaired_df.to_dict(orient="records"))

    print("[corruption_flow] Rebuilding embedding index on repaired data ...")
    repaired_index = LocalEmbeddingIndex.build(
        repaired_df, settings, embeddings_output_path=settings.paths.repaired_embeddings_json
    )

    # 7. Evaluate the repaired dataset.
    print("[corruption_flow] Evaluating repaired dataset ...")
    repaired_bundle = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.repaired_metrics,
        answers_output_path=settings.paths.repaired_answers,
    )
    _print_metrics("Repaired", repaired_bundle.summary)

    print("[corruption_flow] Running data quality checks on repaired data ...")
    repaired_quality = run_data_quality_checks(repaired_df, settings, report_name="repaired")

    print("[corruption_flow] Building freshness report on repaired data ...")
    repaired_freshness_path = settings.paths.quality_dir / "freshness_report_repaired.json"
    repaired_freshness = build_freshness_report(repaired_df, settings, repaired_freshness_path)

    # 8. Generate the comparison report (baseline vs corrupted vs repaired).
    print("[corruption_flow] Generating comparison report ...")
    generate_corruption_report(
        report_path=settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_bundle.summary,
        repaired_metrics=repaired_bundle.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )

    _print_metrics("Baseline", baseline_metrics)
    print(f"[corruption_flow] Done. Comparison report written to {settings.paths.comparison_report}")