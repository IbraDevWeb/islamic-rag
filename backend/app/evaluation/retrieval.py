from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Sequence

import asyncpg

from app.ingestion.openiti import normalize_arabic
from app.search.lexical import LexicalSearchResult, search_lexical


@dataclass(frozen=True)
class RetrievalBenchmarkCase:
    case_id: str
    query: str
    work_uri: str | None
    expected_section_contains: tuple[str, ...]
    k: int = 5
    expected_volume: int | None = None
    expected_page_min: int | None = None
    expected_page_max: int | None = None
    notes: str | None = None


@dataclass(frozen=True)
class RetrievalBenchmark:
    dataset_id: str
    description: str
    label_provenance: str
    cases: tuple[RetrievalBenchmarkCase, ...]


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    query: str
    k: int
    hit: bool
    first_relevant_rank: int | None
    reciprocal_rank: float
    returned_results: int
    expected_section_contains: tuple[str, ...]
    top_section_paths: tuple[tuple[str, ...], ...]
    top_pages: tuple[int | None, ...]


@dataclass(frozen=True)
class RetrievalEvaluationSummary:
    dataset_id: str
    cases: int
    hits: int
    hit_rate: float
    mean_reciprocal_rank: float
    mean_first_relevant_rank: float | None
    all_cases_passed: bool
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


def load_benchmark(path: str | Path) -> RetrievalBenchmark:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("benchmark root must be a JSON object")

    dataset_id = _require_nonempty_string(raw.get("dataset_id"), "dataset_id")
    description = _require_nonempty_string(raw.get("description"), "description")
    label_provenance = _require_nonempty_string(
        raw.get("label_provenance"), "label_provenance"
    )
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
    )


def _is_relevant(case: RetrievalBenchmarkCase, result: LexicalSearchResult) -> bool:
    normalized_path = normalize_arabic(" / ".join(result.section_path))
    for expected in case.expected_section_contains:
        if normalize_arabic(expected) not in normalized_path:
            return False

    if case.expected_volume is not None and result.volume != case.expected_volume:
        return False
    if case.expected_page_min is not None:
        if result.page is None or result.page < case.expected_page_min:
            return False
    if case.expected_page_max is not None:
        if result.page is None or result.page > case.expected_page_max:
            return False
    return True


def evaluate_results(
    case: RetrievalBenchmarkCase,
    results: Sequence[LexicalSearchResult],
) -> RetrievalCaseResult:
    first_rank: int | None = None
    for rank, result in enumerate(results[: case.k], start=1):
        if _is_relevant(case, result):
            first_rank = rank
            break

    return RetrievalCaseResult(
        case_id=case.case_id,
        query=case.query,
        k=case.k,
        hit=first_rank is not None,
        first_relevant_rank=first_rank,
        reciprocal_rank=(1.0 / first_rank) if first_rank is not None else 0.0,
        returned_results=len(results[: case.k]),
        expected_section_contains=case.expected_section_contains,
        top_section_paths=tuple(result.section_path for result in results[: case.k]),
        top_pages=tuple(result.page for result in results[: case.k]),
    )


def summarize_evaluation(
    benchmark: RetrievalBenchmark,
    results: Iterable[RetrievalCaseResult],
) -> RetrievalEvaluationSummary:
    items = tuple(results)
    if len(items) != len(benchmark.cases):
        raise ValueError("evaluation result count does not match benchmark case count")

    hits = sum(1 for item in items if item.hit)
    relevant_ranks = [
        item.first_relevant_rank
        for item in items
        if item.first_relevant_rank is not None
    ]
    return RetrievalEvaluationSummary(
        dataset_id=benchmark.dataset_id,
        cases=len(items),
        hits=hits,
        hit_rate=hits / len(items) if items else 0.0,
        mean_reciprocal_rank=mean(item.reciprocal_rank for item in items)
        if items
        else 0.0,
        mean_first_relevant_rank=mean(relevant_ranks) if relevant_ranks else None,
        all_cases_passed=hits == len(items),
        results=items,
    )


async def run_benchmark(
    conn: asyncpg.Connection,
    benchmark: RetrievalBenchmark,
) -> RetrievalEvaluationSummary:
    case_results: list[RetrievalCaseResult] = []
    for case in benchmark.cases:
        _, search_results = await search_lexical(
            conn,
            case.query,
            limit=case.k,
            work_uri=case.work_uri,
        )
        case_results.append(evaluate_results(case, search_results))

    return summarize_evaluation(benchmark, case_results)
