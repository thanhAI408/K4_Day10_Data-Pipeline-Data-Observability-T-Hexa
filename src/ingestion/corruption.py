from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
from random import Random

import pandas as pd

from core.utils import normalize_whitespace, write_json
from ingestion.cleaning import _format_text_for_embedding


def _pick(df: pd.DataFrame, count: int, seed: Random, exclude: set[int]) -> list[int]:
    pool = [idx for idx in df.index.tolist() if idx not in exclude]
    if not pool or count <= 0:
        return []
    count = min(count, len(pool))
    return seed.sample(pool, count)


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path: Path | str, seed: int = 1337) -> pd.DataFrame:
    """Apply a fixed set of corruptions to demonstrate observability impact."""
    if df.empty:
        write_json(Path(output_log_path), {"skipped": True})
        return df.copy()

    rng = Random(seed)
    corrupted = df.copy()
    log: dict[str, object] = {
        "seed": seed,
        "operations": {},
    }

    # 1. Drop the most recent records (relevance loss / coverage regression).
    drop_n = min(4, max(1, len(corrupted) // 6))
    sorted_idx = (
        corrupted.assign(__published=pd.to_datetime(corrupted["published"], errors="coerce"))
        .sort_values(by="__published", ascending=False)
        .index.tolist()
    )
    drop_idx = sorted_idx[:drop_n]
    corrupted = corrupted.drop(index=drop_idx).reset_index(drop=True)
    log["operations"]["dropped_latest"] = {"count": len(drop_idx), "paper_ids": corrupted.index.tolist() and []}

    used: set[int] = set()

    # 2. Blank summary fields.
    blank_idx = _pick(corrupted, 3, rng, used)
    used.update(blank_idx)
    if blank_idx:
        corrupted.loc[blank_idx, "summary"] = ""
    log["operations"]["blanked_summary"] = {"count": len(blank_idx)}

    # 3. Inject noise into summary fields.
    noise_idx = _pick(corrupted, 3, rng, used)
    used.update(noise_idx)
    if noise_idx:
        corrupted.loc[noise_idx, "summary"] = (
            "<<<NOISE>>> this is corrupted text " + corrupted.loc[noise_idx, "summary"].astype(str)
        )
    log["operations"]["noisy_summary"] = {"count": len(noise_idx)}

    # 4. Truncate the title to eight characters.
    trunc_idx = _pick(corrupted, 2, rng, used)
    used.update(trunc_idx)
    if trunc_idx:
        truncated = corrupted.loc[trunc_idx, "title"].astype(str).str.slice(stop=8)
        truncated = truncated.apply(lambda x: x.rstrip() or x)
        corrupted.loc[trunc_idx, "title"] = truncated.values
    log["operations"]["truncated_title"] = {"count": len(trunc_idx)}

    # 5. Make publication dates stale (2 years older).
    stale_idx = _pick(corrupted, max(2, len(corrupted) // 8), rng, used)
    used.update(stale_idx)
    if stale_idx:
        published_dt = pd.to_datetime(corrupted.loc[stale_idx, "published"], errors="coerce")
        shifted = (published_dt - timedelta(days=365 * 2)).dt.date
        corrupted.loc[stale_idx, "published"] = shifted.astype(str)
    log["operations"]["stale_dates"] = {"count": len(stale_idx), "shift_days": -365 * 2}

    # 6. Add duplicate rows.
    if not corrupted.empty:
        dup_src = _pick(corrupted, 2, rng, used)
        if dup_src:
            duplicates = corrupted.loc[dup_src].copy()
            corrupted = pd.concat([corrupted, duplicates], ignore_index=True)
    log["operations"]["duplicates"] = {"count": len(dup_src) if dup_src else 0}

    # Rebuild text_for_embedding for every row so the corpus reflects corruption.
    corrupted["text_for_embedding"] = corrupted.apply(_format_text_for_embedding, axis=1)
    # Reset age_days after date shifts.
    from datetime import datetime
    run_date = datetime.utcnow()
    parsed = pd.to_datetime(corrupted["published"], errors="coerce")
    corrupted["age_days"] = ((run_date - parsed).dt.days).fillna(-1).astype(int)
    corrupted["title"] = corrupted["title"].astype(str).map(normalize_whitespace)
    corrupted["summary"] = corrupted["summary"].astype(str).map(normalize_whitespace)

    log["final_row_count"] = len(corrupted)
    log["baseline_row_count"] = len(df)
    write_json(Path(output_log_path), log)
    return corrupted.reset_index(drop=True)
