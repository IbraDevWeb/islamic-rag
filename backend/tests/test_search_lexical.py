from app.search.lexical import (
    QueryAnalysis,
    _candidate_sql,
    analyze_query,
    score_candidate,
)


def test_analyze_query_normalizes_and_deduplicates_terms():
    analysis = analyze_query("الصَّلَاة في الصلاة والسَّفَر")

    assert analysis.normalized == "الصلاة في الصلاة والسفر"
    assert analysis.terms == ("الصلاة", "السفر")


def test_analyze_query_detaches_common_proclitics_before_definite_article():
    analysis = analyze_query("والسفر بالصلاة للصوم")

    assert analysis.terms == ("السفر", "الصلاة", "الصوم")


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


def test_section_context_counts_toward_query_coverage():
    analysis = QueryAnalysis(
        original="المياه الوضوء",
        normalized="المياه الوضوء",
        terms=("المياه", "الوضوء"),
    )

    score, matched_terms, phrase_hits, term_hits, section_hits = score_candidate(
        text_normalized="هذا حكم لطهارة مخصوصة",
        section_path=("كتاب الوضوء", "الباب الثالث في المياه"),
        analysis=analysis,
    )

    assert matched_terms == 2
    assert section_hits == 2
    assert phrase_hits == 0
    assert term_hits == 0
    assert score == 151.0


def test_section_context_adds_a_ranking_bonus():
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


def test_candidate_sql_searches_text_and_section_trigram_indexes():
    sql, limit_parameter = _candidate_sql(2)

    assert "c.text_normalized ILIKE $3" in sql
    assert "c.section_text_normalized ILIKE $3" in sql
    assert "c.text_normalized ILIKE $4" in sql
    assert "c.section_text_normalized ILIKE $4" in sql
    assert " OR " in sql
    assert "ORDER BY (CASE WHEN (c.text_normalized ILIKE $3" in sql
    assert "LIMIT $5" in sql
    assert limit_parameter == 5
