from __future__ import annotations

from pathlib import Path

from app.evaluation.retrieval import (
    RetrievalBenchmark,
    RetrievalBenchmarkCase,
    evaluate_results,
    load_benchmark,
    summarize_evaluation,
)
from app.search.lexical import LexicalSearchResult


def _result(*, path: tuple[str, ...], page: int = 1) -> LexicalSearchResult:
    return LexicalSearchResult(
        score=100.0,
        matched_terms=1,
        total_terms=1,
        phrase_hits=0,
        term_hits=1,
        section_hits=1,
        chunk_id="a" * 64,
        sequence_no=1,
        text_original="# نص",
        text_normalized="نص",
        text_hash="b" * 64,
        source_start=10,
        source_end=20,
        volume=1,
        page=page,
        page_side=None,
        section_path=path,
        section_title=path[-1] if path else None,
        content_kind="main_legacy_inferred",
        version_uri="0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1",
        quality_status="UNREVIEWED",
        quality_issues=("PRIMARY_VERSION",),
        source_text_sha256="c" * 64,
        source_metadata_sha256="d" * 64,
        work_uri="0595IbnRushdHafid.BidayatMujtahid",
        work_title=None,
        author_uri="0595IbnRushdHafid",
        author_name="Ibn Rušd al-Ḥafīd",
        provider="OpenITI",
        source_url="https://example.test/source",
        release="test",
        license=None,
        copyright_status=None,
        commercial_use_allowed=None,
        attribution_required=None,
    )


def test_evaluate_results_finds_first_matching_hierarchical_section() -> None:
    case = RetrievalBenchmarkCase(
        case_id="travel-prayer",
        query="الصلاة في السفر",
        work_uri="0595IbnRushdHafid.BidayatMujtahid",
        expected_section_contains=(
            "كتاب الصلاة",
            "الباب الرابع في صلاة السفر",
        ),
        k=5,
    )
    results = [
        _result(path=("كتاب الصلاة", "باب الجمعة")),
        _result(
            path=(
                "كتاب الصلاة",
                "الباب الرابع في صلاة السفر",
                "الفصل الأول في القصر",
            ),
            page=121,
        ),
    ]

    evaluated = evaluate_results(case, results)

    assert evaluated.hit is True
    assert evaluated.first_relevant_rank == 2
    assert evaluated.reciprocal_rank == 0.5
    assert evaluated.top_pages == (1, 121)


def test_evaluate_results_respects_optional_page_constraint() -> None:
    case = RetrievalBenchmarkCase(
        case_id="page-check",
        query="الجمع في السفر",
        work_uri=None,
        expected_section_contains=("الفصل الثاني في الجمع",),
        k=5,
        expected_volume=1,
        expected_page_min=125,
        expected_page_max=130,
    )

    miss = _result(path=("كتاب الصلاة", "الفصل الثاني في الجمع"), page=120)
    hit = _result(path=("كتاب الصلاة", "الفصل الثاني في الجمع"), page=125)

    evaluated = evaluate_results(case, [miss, hit])
    assert evaluated.first_relevant_rank == 2


def test_summarize_evaluation_computes_hit_rate_and_mrr() -> None:
    benchmark = RetrievalBenchmark(
        dataset_id="unit",
        description="unit test",
        label_provenance="unit test",
        cases=(
            RetrievalBenchmarkCase("a", "a", None, ("كتاب",), 5),
            RetrievalBenchmarkCase("b", "b", None, ("باب",), 5),
        ),
    )
    first = evaluate_results(
        benchmark.cases[0],
        [_result(path=("كتاب",))],
    )
    second = evaluate_results(
        benchmark.cases[1],
        [_result(path=("كتاب",))],
    )

    summary = summarize_evaluation(benchmark, [first, second])

    assert summary.cases == 2
    assert summary.hits == 1
    assert summary.hit_rate == 0.5
    assert summary.mean_reciprocal_rank == 0.5
    assert summary.all_cases_passed is False


def test_bidayat_smoke_dataset_is_valid() -> None:
    path = Path(__file__).resolve().parents[1] / "evals" / "retrieval_bidayat_v1.json"
    benchmark = load_benchmark(path)

    assert benchmark.dataset_id == "bidayat-retrieval-smoke-v1"
    assert len(benchmark.cases) == 5
    assert all(case.work_uri == "0595IbnRushdHafid.BidayatMujtahid" for case in benchmark.cases)
