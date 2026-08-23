from __future__ import annotations

import argparse
import json
from time import perf_counter

from app.core.config import settings
from app.search.reranker import RERANKER_ID, _score_query_document_pairs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download/load the local multilingual reranker and run a tiny smoke score. "
            "This does not mutate PostgreSQL, Qdrant, source text, or embeddings."
        )
    )
    parser.add_argument(
        "--query",
        default="الصيام",
        help="Smoke-test query used only for local model inference.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    pairs = [
        (args.query, f"كتاب الصيام\n{args.query}"),
        (args.query, "كتاب البيوع\nالبيع والشراء"),
    ]
    started = perf_counter()
    scores = _score_query_document_pairs(pairs)
    elapsed = perf_counter() - started
    payload = {
        "status": "READY",
        "reranker_id": RERANKER_ID,
        "source_repo": "onnx-community/gte-multilingual-reranker-base",
        "model_file": "onnx/model_quantized.onnx",
        "candidate_pool": settings.reranker_candidate_pool,
        "batch_size": settings.reranker_batch_size,
        "threads": settings.reranker_threads,
        "cache_dir": settings.reranker_cache_dir,
        "smoke_query": args.query,
        "scores": scores,
        "elapsed_seconds": round(elapsed, 3),
        "note": (
            "Higher score means the cross-encoder considers the query/document pair "
            "more relevant. This smoke test is not a retrieval benchmark."
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
