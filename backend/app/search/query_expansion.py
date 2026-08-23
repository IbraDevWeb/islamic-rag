from __future__ import annotations

from dataclasses import dataclass

from app.ingestion.openiti import normalize_arabic

QUERY_EXPANSION_ID = "curated_fiqh_aliases_v1"
MAX_QUERY_VARIANTS = 5


@dataclass(frozen=True)
class QueryAliasGroup:
    canonical: str
    aliases: tuple[str, ...]
    note: str

    @property
    def terms(self) -> tuple[str, ...]:
        return (self.canonical, *self.aliases)


# Retrieval-only terminology aliases. They do not modify source text and must not be
# presented as scholarly/legal equivalence claims. Every addition should be reviewed
# and versioned because it changes candidate generation behaviour.
_ALIAS_GROUPS: tuple[QueryAliasGroup, ...] = (
    QueryAliasGroup(
        canonical="القراض",
        aliases=("المضاربة",),
        note=(
            "Retrieval alias for the known terminology mismatch between the stored "
            "Bidāyat section title كتاب القراض and the query term المضاربة."
        ),
    ),
)


def alias_groups() -> tuple[QueryAliasGroup, ...]:
    return _ALIAS_GROUPS


def expand_query_variants(query: str) -> tuple[str, ...]:
    """Return deterministic normalized query variants from the curated alias registry.

    The original normalized query is always first. Expansion only substitutes terms
    from explicit curated groups and is capped to avoid combinatorial growth.
    """

    normalized = normalize_arabic(query).strip()
    if not normalized:
        raise ValueError("query must not be empty")

    variants: list[str] = [normalized]
    seen = {normalized}

    for group in _ALIAS_GROUPS:
        normalized_terms = tuple(normalize_arabic(term).strip() for term in group.terms)
        for matched in normalized_terms:
            if matched not in normalized:
                continue
            for replacement in normalized_terms:
                if replacement == matched:
                    continue
                candidate = normalized.replace(matched, replacement)
                if candidate in seen:
                    continue
                seen.add(candidate)
                variants.append(candidate)
                if len(variants) >= MAX_QUERY_VARIANTS:
                    return tuple(variants)

    return tuple(variants)
