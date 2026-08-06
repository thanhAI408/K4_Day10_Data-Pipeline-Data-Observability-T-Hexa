from __future__ import annotations

import sys

from core.config import load_settings
from retrieval.index import LocalEmbeddingIndex

SMOKE_QUERIES = [
    "agentic retrieval augmented generation",
    "large language model evaluation",
]


def _check(label: str, condition: bool) -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"[smoke] {status} - {label}")
    return condition


def main() -> int:
    settings = load_settings()

    if not settings.paths.embeddings_json.exists():
        print(
            f"[smoke] Embedding manifest not found at {settings.paths.embeddings_json}. "
            "Build the baseline index first (script/run_phase1.py) before running this smoke test."
        )
        return 1

    index = LocalEmbeddingIndex.load(settings)
    print(f"[smoke] Loaded collection '{index.collection_name}' with {len(index.documents)} documents.")

    all_ok = True

    for query in SMOKE_QUERIES:
        results = index.search(query, top_k=settings.top_k)
        all_ok &= _check(f"semantic_search returns results for query={query!r}", len(results) > 0)
        if results:
            top = results[0]
            all_ok &= _check(
                f"top result for {query!r} has paper_id/title/score/content",
                bool(top.paper_id) and bool(top.title) and top.score >= 0.0 and bool(top.content),
            )

    sample_document = index.documents[0] if index.documents else None
    if sample_document is not None:
        by_id = index.lookup(sample_document["paper_id"])
        all_ok &= _check(f"lookup by paper_id={sample_document['paper_id']!r} finds the document", by_id is not None)

        by_title = index.lookup(sample_document["title"])
        all_ok &= _check(f"lookup by exact title={sample_document['title']!r} finds the document", by_title is not None)

    all_ok &= _check("lookup of a nonexistent id/title returns None", index.lookup("__does_not_exist__") is None)

    if not all_ok:
        print("[smoke] One or more checks failed.")
        return 1

    print("[smoke] All retrieval smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
