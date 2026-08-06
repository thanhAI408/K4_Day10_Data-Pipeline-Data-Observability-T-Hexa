from __future__ import annotations

import logging

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


logger = logging.getLogger(__name__)


def _save_dataframe(df: pd.DataFrame, csv_path, json_path) -> None:
    write_csv(df, csv_path)
    write_json(json_path, df.to_dict(orient="records"))


def main() -> None:
    """Run corruption, re-evaluation, repair and comparison."""
    settings = load_settings()
    if not settings.paths.baseline_metrics.exists():
        raise FileNotFoundError(
            f"Baseline metrics not found at {settings.paths.baseline_metrics}. "
            "Run script/run_phase1.py first."
        )

    if not settings.paths.clean_csv.exists():
        raise FileNotFoundError(f"Clean dataset not found at {settings.paths.clean_csv}.")
    df_clean = pd.read_csv(settings.paths.clean_csv)
    baseline_metrics = read_json(settings.paths.baseline_metrics)

    df_corrupted = corrupt_clean_dataframe(df_clean, settings.paths.corruption_log)
    _save_dataframe(df_corrupted, settings.paths.corrupted_clean_csv, settings.paths.corrupted_clean_json)
    corrupted_index = LocalEmbeddingIndex.build(
        df_corrupted,
        settings,
        settings.paths.corrupted_embeddings_json,
    )
    corrupted_bundle = evaluate_pipeline(
        settings,
        corrupted_index,
        settings.paths.eval_testset,
        settings.paths.corrupted_metrics,
        settings.paths.corrupted_answers,
    )
    corrupted_quality = run_data_quality_checks(df_corrupted, settings, "corrupted_quality")
    corrupted_freshness = build_freshness_report(
        df_corrupted,
        settings,
        settings.paths.quality_dir / "corrupted_freshness_report.json",
    )

    # Repair from the immutable raw snapshot rather than from corrupted data.
    records = load_raw_records(settings.paths.raw_records_json)
    df_repaired = build_clean_dataframe(records, now_utc())
    _save_dataframe(df_repaired, settings.paths.repaired_clean_csv, settings.paths.repaired_clean_json)
    repaired_index = LocalEmbeddingIndex.build(
        df_repaired,
        settings,
        settings.paths.repaired_embeddings_json,
    )
    repaired_bundle = evaluate_pipeline(
        settings,
        repaired_index,
        settings.paths.eval_testset,
        settings.paths.repaired_metrics,
        settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(df_repaired, settings, "repaired_quality")
    repaired_freshness = build_freshness_report(
        df_repaired,
        settings,
        settings.paths.quality_dir / "repaired_freshness_report.json",
    )

    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_bundle.summary,
        repaired_metrics=repaired_bundle.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )

    print("[corruption] baseline=", baseline_metrics)
    print("[corruption] corrupted=", corrupted_bundle.summary)
    print("[corruption] repaired=", repaired_bundle.summary)
    print(f"[corruption] report={settings.paths.comparison_report}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
