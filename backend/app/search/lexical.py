from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import asyncpg

from app.ingestion.openiti import normalize_arabic

WORD_RE = re.compile(r"[\u0621-\u063A\u0641-\u064A\u0660-\u0669A-Za-z0-9]+")
ARABIC_STOPWORDS = {
    "في",
    "من",
    "علي",
    "الي",
    "عن",
    "هل",
    "ما",
    "ماذا",
    "كيف",
    "متي",
    "مع",
    "او",
    "و",
    "ثم",
    "ان",
    "اذا",
    "هذا",
    "هذه",
    "ذلك",
    "تلك",
    "هو",
    "هي",
}


@dataclass(frozen=True)
class QueryAnalysis:
    original: str
    normalized: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class LexicalSearchResult:
    score: float
    matched_terms: int
    total_terms: int
    phrase_hits: int
    term_hits: int
    section_hits: int
    chunk_id: str
    sequence_no: int
    text_original: str
    text_normalized: str
    text_hash: str
    source_start: int
    source_end: int
    volume: int | None
    page: int | None
    page_side: str | None
    section_path: tuple[str, ...]
    section_title: str | None
    content_kind: str
    version_uri: str
    quality_status: str
    quality_issues: tuple[str, ...]
    source_text_sha256: str
    source_metadata_sha256: str
    work_uri: str
    work_title: str | None
    author_uri: str
    author_name: str | None
    provider: str
    source_url: str
    release: str | None
    license: str | None
    copyright_status: str | None
    commercial_use_allowed: bool | None
    attribution_required: bool | None

    @property
    def coverage(self) -> float:
        if self.total_terms == 0:
            return 0.0
        return self.matched_terms / self.total_terms


def analyze_query(query: str) -> QueryAnalysis:
    normalized = normalize_arabic(query)
    raw_terms = WORD_RE.findall(normalized)

    deduplicated: list[str] = []
    seen: set[str] = set()
    for term in raw_terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(term)

    informative = [term for term in deduplicated if term not in ARABIC_STOPWORDS]
    terms = informative or deduplicated
    if not terms:
        raise ValueError("The search query does not contain any searchable terms")

    return QueryAnalysis(
        original=query,
        normalized=normalized,
        terms=tuple(terms),
    )


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


def _count_occurrences(text: str, term: str) -> int:
    return text.count(term)


def score_candidate(
    *,
    text_normalized: str,
    section_path: tuple[str, ...],
    analysis: QueryAnalysis,
) -> tuple[float, int, int, int, int]:
    text = text_normalized
    normalized_section = normalize_arabic(" ".join(section_path)) if section_path else ""

    matched_terms = sum(1 for term in analysis.terms if term in text)
    term_hits = sum(_count_occurrences(text, term) for term in analysis.terms)
    section_hits = sum(1 for term in analysis.terms if term in normalized_section)
    phrase_hits = _count_occurrences(text, analysis.normalized) if analysis.normalized else 0

    coverage = matched_terms / len(analysis.terms)
    score = (
        coverage * 100.0
        + min(phrase_hits, 3) * 25.0
        + min(term_hits, 20) * 2.0
        + section_hits * 5.0
    )
    return score, matched_terms, phrase_hits, term_hits, section_hits


def _candidate_sql(term_count: int) -> tuple[str, int]:
    """Build only trusted SQL fragments; all user values remain bound parameters.

    Explicit OR predicates let PostgreSQL use the pg_trgm GIN index for each
    ILIKE pattern and combine matches with bitmap operations. Candidates that
    match more distinct query terms are considered before the candidate cap.
    """

    if term_count < 1:
        raise ValueError("term_count must be positive")

    first_pattern_parameter = 3
    pattern_parameters = list(
        range(first_pattern_parameter, first_pattern_parameter + term_count)
    )
    predicates = [
        f"c.text_normalized ILIKE ${parameter}"
        for parameter in pattern_parameters
    ]
    coverage_score = " + ".join(
        f"CASE WHEN c.text_normalized ILIKE ${parameter} THEN 1 ELSE 0 END"
        for parameter in pattern_parameters
    )
    limit_parameter = first_pattern_parameter + term_count

    sql = f"""
        SELECT
            c.chunk_id,
            c.sequence_no,
            c.text_original,
            c.text_normalized,
            c.text_hash,
            c.source_start,
            c.source_end,
            c.volume,
            c.page,
            c.page_side,
            c.section_path,
            c.section_title,
            c.content_kind,
            tv.openiti_uri AS version_uri,
            tv.quality_status,
            tv.quality_issues,
            tv.source_text_sha256,
            tv.source_metadata_sha256,
            w.openiti_uri AS work_uri,
            w.title_display AS work_title,
            a.openiti_uri AS author_uri,
            a.name_display AS author_name,
            s.provider,
            s.source_url,
            s.release,
            s.license,
            s.copyright_status,
            s.commercial_use_allowed,
            s.attribution_required
        FROM chunks c
        JOIN text_versions tv ON tv.id = c.version_id
        JOIN works w ON w.id = tv.work_id
        JOIN authors a ON a.id = w.author_id
        JOIN sources s ON s.id = tv.source_id
        WHERE ($1::text IS NULL OR w.openiti_uri = $1)
          AND ($2::boolean OR tv.quality_status <> 'REJECTED')
          AND ({" OR ".join(predicates)})
        ORDER BY ({coverage_score}) DESC, c.id
        LIMIT ${limit_parameter}
    """
    return sql, limit_parameter


async def search_lexical(
    conn: asyncpg.Connection,
    query: str,
    *,
    limit: int = 10,
    candidate_limit: int | None = None,
    work_uri: str | None = None,
    include_rejected: bool = False,
) -> tuple[QueryAnalysis, list[LexicalSearchResult]]:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")

    analysis = analyze_query(query)
    candidate_limit = candidate_limit or max(limit * 50, 250)
    candidate_limit = max(limit, min(candidate_limit, 5000))
    patterns = [f"%{term}%" for term in analysis.terms]
    sql, _ = _candidate_sql(len(patterns))

    rows = await conn.fetch(
        sql,
        work_uri,
        include_rejected,
        *patterns,
        candidate_limit,
    )

    results: list[LexicalSearchResult] = []
    for row in rows:
        section_path = _decode_section_path(row["section_path"])
        score, matched_terms, phrase_hits, term_hits, section_hits = score_candidate(
            text_normalized=row["text_normalized"],
            section_path=section_path,
            analysis=analysis,
        )
        results.append(
            LexicalSearchResult(
                score=score,
                matched_terms=matched_terms,
                total_terms=len(analysis.terms),
                phrase_hits=phrase_hits,
                term_hits=term_hits,
                section_hits=section_hits,
                chunk_id=row["chunk_id"],
                sequence_no=row["sequence_no"],
                text_original=row["text_original"],
                text_normalized=row["text_normalized"],
                text_hash=row["text_hash"],
                source_start=row["source_start"],
                source_end=row["source_end"],
                volume=row["volume"],
                page=row["page"],
                page_side=row["page_side"],
                section_path=section_path,
                section_title=row["section_title"],
                content_kind=row["content_kind"],
                version_uri=row["version_uri"],
                quality_status=row["quality_status"],
                quality_issues=tuple(row["quality_issues"] or ()),
                source_text_sha256=row["source_text_sha256"],
                source_metadata_sha256=row["source_metadata_sha256"],
                work_uri=row["work_uri"],
                work_title=row["work_title"],
                author_uri=row["author_uri"],
                author_name=row["author_name"],
                provider=row["provider"],
                source_url=row["source_url"],
                release=row["release"],
                license=row["license"],
                copyright_status=row["copyright_status"],
                commercial_use_allowed=row["commercial_use_allowed"],
                attribution_required=row["attribution_required"],
            )
        )

    results.sort(
        key=lambda result: (
            -result.score,
            -result.matched_terms,
            -result.phrase_hits,
            -result.term_hits,
            result.sequence_no,
        )
    )
    return analysis, results[:limit]
