from __future__ import annotations

import argparse
import asyncio
import json

import asyncpg

from app.core.config import settings
from app.evaluation.retrieval import load_benchmark, run_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate retrieval against a manually labelled, corpus-validated benchmark."
        )
    )
    parser.add_argument(
        "--dataset",
        default="evals/retrieval_bidayat_baseline_v2.json",
        help="Path to a retrieval benchmark JSON file.",
    )
    parser.add_argument(
        "--fail-under-hit-rate",
        type=float,
        default=None,
        help="Exit non-zero if Hit@k rate is below this threshold (0.0-1.0).",
    )
    parser.add_argument(
        "--fail-under-pass-rate",
        type=float,
        default=None,
        help=(
            "Exit non-zero if strict case pass-rate is below this threshold. "
            "A case passes only when the first relevant result is within its "
            "configured max_first_relevant_rank."
        ),
    )
    parser.add_argument(
        "--fail-under-hit-at-1",
        type=float,
        default=None,
        help="Exit non-zero if Hit@1 rate is below this threshold (0.0-1.0).",
    )
    parser.add_argument(
        "--fail-under-mrr",
        type=float,
        default=None,
        help="Exit non-zero if mean reciprocal rank is below this threshold (0.0-1.0).",
    )
    parser.add_argument(
        "--skip-label-validation",
        action="store_true",
        help=(
            "Skip checking that every labelled target section exists in the current "
            "corpus. Intended only for benchmark authoring/debugging."
        ),
    )
    return parser


def _validate_threshold(value: float | None, name: str) -> None:
    if value is not None and not 0 <= value <= 1:
        raise SystemExit(f"{name} must be between 0.0 and 1.0")


async def _run(args: argparse.Namespace) -> int:
    thresholds = {
        "--fail-under-hit-rate": args.fail_under_hit_rate,
        "--fail-under-pass-rate": args.fail_under_pass_rate,
        "--fail-under-hit-at-1": args.fail_under_hit_at_1,
        "--fail-under-mrr": args.fail_under_mrr,
    }
    for name, value in thresholds.items():
        _validate_threshold(value, name)

    benchmark = load_benchmark(args.dataset)
    conn = await asyncpg.connect(settings.postgres_dsn)
    try:
        summary = await run_benchmark(
            conn,
            benchmark,
            validate_labels=not args.skip_label_validation,
        )
    finally:
        await conn.close()

    failures: list[dict[str, float | str]] = []
    checks = (
        ("hit_rate", summary.hit_rate, args.fail_under_hit_rate),
        ("pass_rate", summary.pass_rate, args.fail_under_pass_rate),
        ("hit_rate_at_1", summary.hit_rate_at_1, args.fail_under_hit_at_1),
        ("mean_reciprocal_rank", summary.mean_reciprocal_rank, args.fail_under_mrr),
    )
    for metric, actual, minimum in checks:
        if minimum is not None and actual < minimum:
            failures.append(
                {
                    "metric": metric,
                    "actual": actual,
                    "minimum": minimum,
                }
            )

    payload = summary.to_dict()
    payload["description"] = benchmark.description
    payload["label_provenance"] = benchmark.label_provenance
    payload["threshold_failures"] = failures
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 2 if failures else 0


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
