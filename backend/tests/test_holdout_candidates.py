from app.cli.propose_holdout_sections import (
    filter_unused_sections,
    used_top_level_sections,
)
from app.evaluation.retrieval import RetrievalBenchmark, RetrievalBenchmarkCase


def _benchmark() -> RetrievalBenchmark:
    return RetrievalBenchmark(
        dataset_id="unit",
        description="unit",
        label_provenance="unit",
        cases=(
            RetrievalBenchmarkCase(
                case_id="a",
                query="q1",
                work_uri="work",
                expected_section_contains=("كتاب الصلاة", "باب السفر"),
            ),
            RetrievalBenchmarkCase(
                case_id="b",
                query="q2",
                work_uri="work",
                expected_section_contains=("كتاب الوضوء",),
            ),
        ),
    )


def test_used_top_level_sections_extracts_first_kitab_fragment() -> None:
    assert used_top_level_sections(_benchmark()) == {"كتاب الصلاة", "كتاب الوضوء"}


def test_filter_unused_sections_excludes_tuning_sections_and_small_sections() -> None:
    rows = [
        {"top_section": "كتاب الصلاة", "chunks": 10, "first_page": 1, "last_page": 5},
        {"top_section": "كتاب الحج", "chunks": 8, "first_page": 10, "last_page": 20},
        {"top_section": "كتاب نادر", "chunks": 1, "first_page": 21, "last_page": 21},
    ]

    assert filter_unused_sections(
        rows,
        used_sections={"كتاب الصلاة"},
        min_chunks=2,
    ) == [
        {"top_section": "كتاب الحج", "chunks": 8, "first_page": 10, "last_page": 20}
    ]
