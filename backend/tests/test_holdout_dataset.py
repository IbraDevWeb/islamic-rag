from pathlib import Path

from app.evaluation.retrieval import load_benchmark


EVALS = Path("evals")
TUNING_DATASET = EVALS / "retrieval_bidayat_baseline_v2.json"
HOLDOUT_DATASET = EVALS / "retrieval_bidayat_holdout_v1.json"


def _top_level_sections(dataset) -> set[str]:
    sections: set[str] = set()
    for case in dataset.cases:
        for fragment in case.expected_section_contains:
            if fragment.startswith("كتاب "):
                sections.add(fragment)
                break
    return sections


def test_frozen_holdout_loads_and_has_expected_size() -> None:
    holdout = load_benchmark(HOLDOUT_DATASET)

    assert holdout.dataset_id == "bidayat-retrieval-holdout-v1"
    assert holdout.schema_version == 2
    assert len(holdout.cases) == 26
    assert len({case.case_id for case in holdout.cases}) == 26
    assert all(case.case_id.startswith("holdout-") for case in holdout.cases)
    assert all(case.required_rank <= case.k for case in holdout.cases)


def test_holdout_top_level_sections_are_disjoint_from_tuning_dataset() -> None:
    tuning = load_benchmark(TUNING_DATASET)
    holdout = load_benchmark(HOLDOUT_DATASET)

    tuning_sections = _top_level_sections(tuning)
    holdout_sections = _top_level_sections(holdout)

    assert holdout_sections
    assert tuning_sections.isdisjoint(holdout_sections)


def test_holdout_contains_nontrivial_query_slices() -> None:
    holdout = load_benchmark(HOLDOUT_DATASET)
    query_types = {case.query_type for case in holdout.cases}
    difficulties = {case.difficulty for case in holdout.cases}

    assert {"direct", "clitic", "structural", "morphology", "paraphrase", "topic_discrimination"} <= query_types
    assert {"easy", "medium", "hard"} <= difficulties
