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


def _case(
    case_id: str,
    expected: tuple[str, ...],
    *,
    max_rank: int = 5,
    query_type: str = "direct",
    difficulty: str = "medium",
) -> RetrievalBenchmarkCase:
    return RetrievalBenchmarkCase(
        case_id=case_id,
        query=case_id,
        work_uri="0595IbnRushdHafid.BidayatMujtahid",
        expected_section_contains=expected,
        k=5,
        max_first_relevant_rank=max_rank,
        query_type=query_type,
        difficulty=difficulty,
    )


def test_evaluate_results_reports_rank_precision_and_strict_pass() -> None:
    case = _case(
        "travel-prayer",
        ("كتاب الصلاة", "الباب الرابع في صلاة السفر"),
        max_rank=1,
        query_type="structural",
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
        _result(
            path=(
                "كتاب الصلاة",
                "الباب الرابع في صلاة السفر",
                "الفصل الثاني في الجمع",
            ),
            page=125,
        ),
    ]

    evaluated = evaluate_results(case, results, latency_ms=12.3456)

    assert evaluated.hit is True
    assert evaluated.hit_at_1 is False
    assert evaluated.hit_at_3 is True
    assert evaluated.passed is False
    assert evaluated.first_relevant_rank == 2
    assert evaluated.reciprocal_rank == 0.5
    assert evaluated.relevant_results_in_top_k == 2
    assert evaluated.precision_at_k == 0.4
    assert evaluated.latency_ms == 12.346
    assert evaluated.top_pages == (1, 121, 125)


def test_evaluate_results_respects_optional_page_constraint() -> None:
    case = RetrievalBenchmarkCase(
        case_id="page-check",
        query="الجمع في السفر",
        work_uri=None,
        expected_section_contains=("الفصل الثاني في الجمع",),
        k=5,
        max_first_relevant_rank=3,
        query_type="structural",
        difficulty="medium",
        expected_volume=1,
        expected_page_min=125,
        expected_page_max=130,
    )

    miss = _result(path=("كتاب الصلاة", "الفصل الثاني في الجمع"), page=120)
    hit = _result(path=("كتاب الصلاة", "الفصل الثاني في الجمع"), page=125)

    evaluated = evaluate_results(case, [miss, hit])
    assert evaluated.first_relevant_rank == 2
    assert evaluated.passed is True


def test_summarize_evaluation_computes_rank_metrics_and_slices() -> None:
    first_case = _case(
        "a",
        ("كتاب",),
        max_rank=1,
        query_type="direct",
        difficulty="easy",
    )
    second_case = _case(
        "b",
        ("باب",),
        max_rank=3,
        query_type="morphology",
        difficulty="hard",
    )
    benchmark = RetrievalBenchmark(
        dataset_id="unit",
        description="unit test",
        label_provenance="unit test",
        cases=(first_case, second_case),
        schema_version=2,
        benchmark_sha256="e" * 64,
    )
    first = evaluate_results(
        first_case,
        [_result(path=("كتاب",))],
        latency_ms=10.0,
    )
    second = evaluate_results(
        second_case,
        [_result(path=("كتاب",))],
        latency_ms=30.0,
    )

    summary = summarize_evaluation(
        benchmark,
        [first, second],
        corpus_fingerprint="f" * 64,
    )

    assert summary.cases == 2
    assert summary.passes == 1
    assert summary.hits == 1
    assert summary.pass_rate == 0.5
    assert summary.hit_rate == 0.5
    assert summary.hit_rate_at_1 == 0.5
    assert summary.hit_rate_at_3 == 0.5
    assert summary.mean_reciprocal_rank == 0.5
    assert summary.mean_precision_at_k == 0.1
    assert summary.median_latency_ms == 20.0
    assert summary.p95_latency_ms == 30.0
    assert summary.by_query_type["direct"]["pass_rate"] == 1.0
    assert summary.by_query_type["morphology"]["pass_rate"] == 0.0
    assert summary.by_difficulty["easy"]["hit_rate_at_1"] == 1.0
    assert summary.by_difficulty["hard"]["hit_rate_at_1"] == 0.0
    assert summary.all_cases_passed is False


def test_bidayat_smoke_dataset_remains_valid() -> None:
    path = Path(__file__).resolve().parents[1] / "evals" / "retrieval_bidayat_v1.json"
    benchmark = load_benchmark(path)

    assert benchmark.dataset_id == "bidayat-retrieval-smoke-v1"
    assert len(benchmark.cases) == 6
    assert len(benchmark.benchmark_sha256) == 64
    assert all(
        case.work_uri == "0595IbnRushdHafid.BidayatMujtahid"
        for case in benchmark.cases
    )


def test_demanding_bidayat_baseline_is_large_and_sliced() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "evals"
        / "retrieval_bidayat_baseline_v2.json"
    )
    benchmark = load_benchmark(path)

    assert benchmark.dataset_id == "bidayat-retrieval-baseline-v2"
    assert benchmark.schema_version == 2
    assert len(benchmark.cases) >= 45
    assert len(benchmark.benchmark_sha256) == 64

    query_types = {case.query_type for case in benchmark.cases}
    difficulties = {case.difficulty for case in benchmark.cases}
    assert {"direct", "structural", "clitic", "morphology", "paraphrase"} <= query_types
    assert difficulties == {"easy", "medium", "hard"}
    assert any(case.max_first_relevant_rank == 1 for case in benchmark.cases)
    assert any(case.max_first_relevant_rank == 5 for case in benchmark.cases)
