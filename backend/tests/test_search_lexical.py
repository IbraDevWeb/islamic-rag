from app.search.lexical import QueryAnalysis, analyze_query, score_candidate


def test_analyze_query_normalizes_and_deduplicates_terms():
    analysis = analyze_query("الصَّلَاة في الصلاة والسَّفَر")

    assert analysis.normalized == "الصلاة في الصلاة والسفر"
    assert analysis.terms == ("الصلاة", "والسفر")


def test_score_prefers_full_term_coverage_and_exact_phrase():
    analysis = QueryAnalysis(
        original="الصلاة السفر",
        normalized="الصلاة السفر",
        terms=("الصلاة", "السفر"),
    )

    exact = score_candidate(
        text_normalized="باب الصلاة السفر وفيه احكام الصلاة",
        section_path=("كتاب الصلاة", "باب السفر"),
        analysis=analysis,
    )
    partial = score_candidate(
        text_normalized="باب الصلاة وفيه احكام الصلاة",
        section_path=("كتاب الصلاة",),
        analysis=analysis,
    )

    assert exact[0] > partial[0]
    assert exact[1] == 2
    assert exact[2] == 1
    assert partial[1] == 1


def test_section_context_adds_a_small_ranking_bonus():
    analysis = QueryAnalysis(
        original="السفر",
        normalized="السفر",
        terms=("السفر",),
    )

    with_section = score_candidate(
        text_normalized="احكام السفر",
        section_path=("كتاب الصلاة", "باب السفر"),
        analysis=analysis,
    )
    without_section = score_candidate(
        text_normalized="احكام السفر",
        section_path=(),
        analysis=analysis,
    )

    assert with_section[0] > without_section[0]
