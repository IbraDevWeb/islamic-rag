from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Any, Iterable, Sequence

import asyncpg

from app.ingestion.openiti import normalize_arabic
from app.search.lexical import RETRIEVAL_ID, LexicalSearchResult, search_lexical


@dataclass(frozen=True)
class RetrievalBenchmarkCase:
    case_id: str
    query: str
    work_uri: str | None
    expected_section_contains: tuple[str, ...]
    k: int = 5
    max_first_relevant_rank: int | None = None
    query_type: str = "direct"
    difficulty: str = "medium"
    expected_volume: int | None = None
    expected_page_min: int | None = None
    expected_page_max: int | None = None
    notes: str | None = None

    @property
    def required_rank(self) -> int:
        return self.max_first_relevant_rank or self.k


@dataclass(frozen=True)
class RetrievalBenchmark:
    dataset_id: str
    description: str
    label_provenance: str
    cases: tuple[RetrievalBenchmarkCase, ...]
    schema_version: int = 1
    benchmark_sha256: str = ""


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    query: str
    query_type: str
    difficulty: str
    k: int
    max_first_relevant_rank: int
    passed: bool
    hit: bool
    hit_at_1: bool
    hit_at_3: bool
    first_relevant_rank: int | None
    reciprocal_rank: float
    relevant_results_in_top_k: int
    precision_at_k: float
    returned_results: int
    latency_ms: float
    expected_section_contains: tuple[str, ...]
    top_section_paths: tuple[tuple[str, ...], ...]
    top_pages: tuple[int | None, ...]


@dataclass(frozen=True)
class RetrievalEvaluationSummary:
    dataset_id: str
    schema_version: int
    benchmark_sha256: str
    corpus_fingerprint: str
    retrieval_id: str
    cases: int
    passes: int
    hits: int
    pass_rate: float
    hit_rate: float
    hit_rate_at_1: float
    hit_rate_at_3: float
    mean_reciprocal_rank: float
    mean_first_relevant_rank: float | None
    mean_precision_at_k: float
    median_latency_ms: float
    p95_latency_ms: float
    all_cases_passed: bool
    by_query_type: dict[str, dict[str, float | int | None]]
    by_difficulty: dict[str, dict[str, float | int | None]]
    results: tuple[RetrievalCaseResult, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["results"] = [asdict(result) for result in self.results]
        return payload


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer or null")
    return value


def _decode_section_path(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return (value,)
    else:
        decoded = value
    if isinstance(decoded, list):
        return tuple(str(item) for item in decoded if item)
    return (str(decoded),)


def load_benchmark(path: str | Path) -> RetrievalBenchmark:
    benchmark_path = Path(path)
    raw_bytes = benchmark_path.read_bytes()
    raw = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("benchmark root must be a JSON object")

    dataset_id = _require_nonempty_string(raw.get("dataset_id"), "dataset_id")
    description = _require_nonempty_string(raw.get("description"), "description")
    label_provenance = _require_nonempty_string(
        raw.get("label_provenance"), "label_provenance"
    )
    schema_version = raw.get("schema_version", 1)
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise ValueError("schema_version must be an integer")
    if schema_version < 1:
        raise ValueError("schema_version must be positive")

    raw_cases = raw.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("cases must be a non-empty array")

    cases: list[RetrievalBenchmarkCase] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_cases):
        if not isinstance(item, dict):
            raise ValueError(f"cases[{index}] must be an object")

        case_id = _require_nonempty_string(item.get("id"), f"cases[{index}].id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate benchmark case id: {case_id}")
        seen_ids.add(case_id)

        query = _require_nonempty_string(item.get("query"), f"cases[{index}].query")
        work_uri_value = item.get("work_uri")
        work_uri = (
            _require_nonempty_string(work_uri_value, f"cases[{index}].work_uri")
            if work_uri_value is not None
            else None
        )

        expected = item.get("expected_section_contains", [])
        if not isinstance(expected, list) or not expected:
            raise ValueError(
                f"cases[{index}].expected_section_contains must be a non-empty array"
            )
        expected_sections = tuple(
            _require_nonempty_string(value, f"cases[{index}].expected_section_contains")
            for value in expected
        )

        k = item.get("k", 5)
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 50:
            raise ValueError(f"cases[{index}].k must be between 1 and 50")

        max_rank = item.get("max_first_relevant_rank", k)
        if (
            isinstance(max_rank, bool)
            or not isinstance(max_rank, int)
            or not 1 <= max_rank <= k
        ):
            raise ValueError(
                f"cases[{index}].max_first_relevant_rank must be between 1 and k"
            )

        query_type = _require_nonempty_string(
            item.get("query_type", "direct"), f"cases[{index}].query_type"
        )
        difficulty = _require_nonempty_string(
            item.get("difficulty", "medium"), f"cases[{index}].difficulty"
        )
        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError(
                f"cases[{index}].difficulty must be easy, medium, or hard"
            )

        page_min = _optional_int(item.get("expected_page_min"), "expected_page_min")
        page_max = _optional_int(item.get("expected_page_max"), "expected_page_max")
        if page_min is not None and page_max is not None and page_min > page_max:
            raise ValueError(f"cases[{index}] expected_page_min exceeds expected_page_max")

        cases.append(
            RetrievalBenchmarkCase(
                case_id=case_id,
                query=query,
                work_uri=work_uri,
                expected_section_contains=expected_sections,
                k=k,
                max_first_relevant_rank=max_rank,
                query_type=query_type,
                difficulty=difficulty,
                expected_volume=_optional_int(
                    item.get("expected_volume"), "expected_volume"
                ),
                expected_page_min=page_min,
                expected_page_max=page_max,
                notes=item.get("notes") if isinstance(item.get("notes"), str) else None,
            )
        )

    return RetrievalBenchmark(
        dataset_id=dataset_id,
        description=description,
        label_provenance=label_provenance,
        cases=tuple(cases),
        schema_version=schema_version,
        benchmark_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def _location_is_relevant(
    case: RetrievalBenchmarkCase,
    section_path: Sequence[str],
    volume: int | None,
    page: int | None,
) -> bool:
    normalized_path = normalize_arabic(" / ".join(section_path))
    for expected in case.expected_section_contains:
        if normalize_arabic(expected) not in normalized_path:
            return False

    if case.expected_volume is not None and volume != case.expected_volume:
        return False
    if case.expected_page_min is not None:
        if page is None or page < case.expected_page_min:
            return False
    if case.expected_page_max is not None:
        if page is None or page > case.expected_page_max:
            return False
    return True


def _is_relevant(case: RetrievalBenchmarkCase, result: LexicalSearchResult) -> bool:
    return _location_is_relevant(
        case,
        result.section_path,
        result.volume,
        result.page,
    )


def evaluate_results(
    case: RetrievalBenchmarkCase,
    results: Sequence[LexicalSearchResult],
    *,
    latency_ms: float = 0.0,
) -> RetrievalCaseResult:
    inspected = tuple(results[: case.k])
    relevance = tuple(_is_relevant(case, result) for result in inspected)
    first_rank = next(
        (rank for rank, is_relevant in enumerate(relevance, start=1) if is_relevant),
        None,
    )
    relevant_count = sum(1 for value in relevance if value)

    return RetrievalCaseResult(
        case_id=case.case_id,
        query=case.query,
        query_type=case.query_type,
        difficulty=case.difficulty,
        k=case.k,
        max_first_relevant_rank=case.required_rank,
        passed=first_rank is not None and first_rank <= case.required_rank,
        hit=first_rank is not None,
        hit_at_1=first_rank == 1,
        hit_at_3=first_rank is not None and first_rank <= min(3, case.k),
        first_relevant_rank=first_rank,
        reciprocal_rank=(1.0 / first_rank) if first_rank is not None else 0.0,
        relevant_results_in_top_k=relevant_count,
        precision_at_k=relevant_count / case.k,
        returned_results=len(inspected),
        latency_ms=round(latency_ms, 3),
        expected_section_contains=case.expected_section_contains,
        top_section_paths=tuple(result.section_path for result in inspected),
        top_pages=tuple(result.page for result in inspected),
    )


def _nearest_rank_percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percentile * len(ordered) + 0.999999)) - 1))
    return ordered[index]


def _aggregate_results(
    items: Sequence[RetrievalCaseResult],
) -> dict[str, float | int | None]:
    if not items:
        return {
            "cases": 0,
            "passes": 0,
            "pass_rate": 0.0,
            "hit_rate": 0.0,
            "hit_rate_at_1": 0.0,
            "hit_rate_at_3": 0.0,
            "mean_reciprocal_rank": 0.0,
            "mean_first_relevant_rank": None,
            "mean_precision_at_k": 0.0,
        }

    relevant_ranks = [
        item.first_relevant_rank
        for item in items
        if item.first_relevant_rank is not None
    ]
    total = len(items)
    return {
        "cases": total,
        "passes": sum(1 for item in items if item.passed),
        "pass_rate": sum(1 for item in items if item.passed) / total,
        "hit_rate": sum(1 for item in items if item.hit) / total,
        "hit_rate_at_1": sum(1 for item in items if item.hit_at_1) / total,
        "hit_rate_at_3": sum(1 for item in items if item.hit_at_3) / total,
        "mean_reciprocal_rank": mean(item.reciprocal_rank for item in items),
        "mean_first_relevant_rank": mean(relevant_ranks) if relevant_ranks else None,
        "mean_precision_at_k": mean(item.precision_at_k for item in items),
    }


def _slice_metrics(
    items: Sequence[RetrievalCaseResult],
    attribute: str,
) -> dict[str, dict[str, float | int | None]]:
    values = sorted({str(getattr(item, attribute)) for item in items})
    return {
        value: _aggregate_results(
            [item for item in items if str(getattr(item, attribute)) == value]
        )
        for value in values
    }


def summarize_evaluation(
    benchmark: RetrievalBenchmark,
    results: Iterable[RetrievalCaseResult],
    *,
    corpus_fingerprint: str = "",
) -> RetrievalEvaluationSummary:
    items = tuple(results)
    if len(items) != len(benchmark.cases):
        raise ValueError("evaluation result count does not match benchmark case count")

    aggregate = _aggregate_results(items)
    latency_values = [item.latency_ms for item in items]
    return RetrievalEvaluationSummary(
        dataset_id=benchmark.dataset_id,
        schema_version=benchmark.schema_version,
        benchmark_sha256=benchmark.benchmark_sha256,
        corpus_fingerprint=corpus_fingerprint,
        retrieval_id=RETRIEVAL_ID,
        cases=len(items),
        passes=int(aggregate["passes"] or 0),
        hits=sum(1 for item in items if item.hit),
        pass_rate=float(aggregate["pass_rate"] or 0.0),
        hit_rate=float(aggregate["hit_rate"] or 0.0),
        hit_rate_at_1=float(aggregate["hit_rate_at_1"] or 0.0),
        hit_rate_at_3=float(aggregate["hit_rate_at_3"] or 0.0),
        mean_reciprocal_rank=float(aggregate["mean_reciprocal_rank"] or 0.0),
        mean_first_relevant_rank=(
            float(aggregate["mean_first_relevant_rank"])
            if aggregate["mean_first_relevant_rank"] is not None
            else None
        ),
        mean_precision_at_k=float(aggregate["mean_precision_at_k"] or 0.0),
        median_latency_ms=round(median(latency_values), 3) if latency_values else 0.0,
        p95_latency_ms=round(_nearest_rank_percentile(latency_values, 0.95), 3),
        all_cases_passed=all(item.passed for item in items),
        by_query_type=_slice_metrics(items, "query_type"),
        by_difficulty=_slice_metrics(items, "difficulty"),
        results=items,
    )


async def validate_benchmark_against_corpus(
    conn: asyncpg.Connection,
    benchmark: RetrievalBenchmark,
) -> None:
    """Reject labels that do not correspond to any stored corpus location.

    This validation prevents a benchmark typo or invented section label from
    being interpreted as a retrieval failure. It validates label existence,
    not scholarly relevance of the query itself.
    """

    cases_by_work: dict[str | None, list[RetrievalBenchmarkCase]] = {}
    for case in benchmark.cases:
        cases_by_work.setdefault(case.work_uri, []).append(case)

    failures: list[str] = []
    for work_uri, cases in cases_by_work.items():
        rows = await conn.fetch(
            """
            SELECT DISTINCT c.section_path, c.volume, c.page
            FROM chunks c
            JOIN text_versions tv ON tv.id = c.version_id
            JOIN works w ON w.id = tv.work_id
            WHERE ($1::text IS NULL OR w.openiti_uri = $1)
            """,
            work_uri,
        )
        locations = [
            (
                _decode_section_path(row["section_path"]),
                row["volume"],
                row["page"],
            )
            for row in rows
        ]
        for case in cases:
            if not any(
                _location_is_relevant(case, path, volume, page)
                for path, volume, page in locations
            ):
                failures.append(
                    f"{case.case_id}: no corpus location matches "
                    f"{list(case.expected_section_contains)!r}"
                )

    if failures:
        joined = "; ".join(failures)
        raise ValueError(f"benchmark label validation failed: {joined}")


async def corpus_fingerprint(
    conn: asyncpg.Connection,
    benchmark: RetrievalBenchmark,
) -> str:
    work_uris = sorted(
        {case.work_uri for case in benchmark.cases if case.work_uri is not None}
    )
    if len(work_uris) == len({case.work_uri for case in benchmark.cases}):
        rows = await conn.fetch(
            """
            SELECT
                w.openiti_uri AS work_uri,
                tv.openiti_uri AS version_uri,
                tv.source_text_sha256,
                tv.source_metadata_sha256,
                tv.quality_status,
                s.provider,
                s.release
            FROM text_versions tv
            JOIN works w ON w.id = tv.work_id
            JOIN sources s ON s.id = tv.source_id
            WHERE w.openiti_uri = ANY($1::text[])
            ORDER BY w.openiti_uri, tv.openiti_uri
            """,
            work_uris,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT
                w.openiti_uri AS work_uri,
                tv.openiti_uri AS version_uri,
                tv.source_text_sha256,
                tv.source_metadata_sha256,
                tv.quality_status,
                s.provider,
                s.release
            FROM text_versions tv
            JOIN works w ON w.id = tv.work_id
            JOIN sources s ON s.id = tv.source_id
            ORDER BY w.openiti_uri, tv.openiti_uri
            """
        )

    payload = [dict(row) for row in rows]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def run_benchmark(
    conn: asyncpg.Connection,
    benchmark: RetrievalBenchmark,
    *,
    validate_labels: bool = True,
) -> RetrievalEvaluationSummary:
    if validate_labels:
        await validate_benchmark_against_corpus(conn, benchmark)
    fingerprint = await corpus_fingerprint(conn, benchmark)

    case_results: list[RetrievalCaseResult] = []
    for case in benchmark.cases:
        started = perf_counter()
        _, search_results = await search_lexical(
            conn,
            case.query,
            limit=case.k,
            work_uri=case.work_uri,
        )
        latency_ms = (perf_counter() - started) * 1000.0
        case_results.append(
            evaluate_results(case, search_results, latency_ms=latency_ms)
        )

    return summarize_evaluation(
        benchmark,
        case_results,
        corpus_fingerprint=fingerprint,
    )
