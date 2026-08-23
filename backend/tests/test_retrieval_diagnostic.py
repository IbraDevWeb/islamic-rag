from types import SimpleNamespace

from app.cli.diagnose_retrieval_case import (
    _branch_payload,
    _first_relevant_rank,
    _result_is_relevant,
)
from app.evaluation.retrieval import RetrievalBenchmarkCase


def _case() -> RetrievalBenchmarkCase:
    return RetrievalBenchmarkCase(
        case_id="qirad",
        query="المضاربة",
        work_uri="work",
        expected_section_contains=("كتاب القراض",),
        k=5,
        max_first_relevant_rank=5,
        query_type="paraphrase",
        difficulty="hard",
    )


def _result(section: str, page: int, score: float = 1.0):
    return SimpleNamespace(
        score=score,
        chunk_id=f"chunk-{page}",
        page=page,
        volume=None,
        section_path=(section,),
    )


def test_diagnostic_finds_relevant_candidate_beyond_original_k() -> None:
    case = _case()
    results = [_result("كتاب آخر", page) for page in range(1, 7)]
    results.append(_result("كتاب القراض", 7))

    assert _first_relevant_rank(case, results) == 7
    payload = _branch_payload(case, results, show=7)
    assert payload["hit_within_original_k"] is False
    assert payload["hit_within_depth"] is True
    assert payload["reranker_candidate_status"] == "recoverable_from_deeper_pool"
    assert payload["results"][-1]["relevant"] is True


def test_diagnostic_reports_missing_candidate_pool() -> None:
    case = _case()
    results = [_result("كتاب آخر", page) for page in range(1, 11)]

    assert _first_relevant_rank(case, results) is None
    payload = _branch_payload(case, results, show=5)
    assert payload["hit_within_depth"] is False
    assert payload["reranker_candidate_status"] == "missing_from_candidate_pool"


def test_relevance_uses_normalized_section_path() -> None:
    case = _case()
    result = _result("كِتابُ القِراض", 10)

    assert _result_is_relevant(case, result) is True
