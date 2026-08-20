from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable

from app.ingestion.openiti import (
    PAGE_RE,
    PARATEXT_RE,
    OpenITIChunk,
    OpenITIDocument,
    normalize_arabic,
    sha256_text,
)

# Some OpenITI source versions contain legacy-looking lines such as
# "# | كتاب الطهارة" instead of the standard structural tag "### | ...".
# Official OpenITI mARkdown treats a single "# " as a paragraph marker, so
# these lines are never promoted as authoritative OpenITI headers.  We only
# derive a conservative structure when the entire text has no explicit
# "### |" headers, and we mark resulting chunks as inferred.
EXPLICIT_SECTION_RE = re.compile(r"(?m)^###\s+\|+")
LEGACY_PIPE_RE = re.compile(r"^#\s+\|\s*(?P<title>.*?)\s*$")
LEGACY_MILESTONE_RE = re.compile(r"\b(?:ms|Milestone)\d+\b", re.IGNORECASE)
LEGACY_CONTENT_KIND = "main_legacy_inferred"


@dataclass(frozen=True)
class _PageSpan:
    start: int
    end: int
    volume: int | None
    page: int | None
    side: str | None


@dataclass(frozen=True)
class _StructuralSpan:
    start: int
    end: int
    section_path: tuple[str, ...]
    content_kind: str


def _clean_title(title: str) -> str:
    value = LEGACY_MILESTONE_RE.sub(" ", title)
    return re.sub(r"\s+", " ", value).strip()


def _legacy_heading_level(title: str) -> int | None:
    """Return an inferred hierarchy level for conservative Arabic heading cues."""

    value = _clean_title(title)
    if value == "كتاب" or value.startswith("كتاب "):
        return 1
    if value.startswith(("الباب ", "باب ")) or value in {"الباب", "باب"}:
        return 2
    if value.startswith(
        ("الفصل ", "فصل ", "القسم ", "قسم ", "النوع ", "نوع ")
    ) or value in {"الفصل", "فصل", "القسم", "قسم", "النوع", "نوع"}:
        return 3
    if value.startswith(
        ("المسألة ", "مسألة ", "المبحث ", "مبحث ", "الفرع ", "فرع ")
    ) or value in {"المسألة", "مسألة", "المبحث", "مبحث", "الفرع", "فرع"}:
        return 4
    return None


def _parse_header(line: str) -> tuple[int, str, str] | None:
    stripped = line.strip()

    # Preserve real OpenITI paratext markers even in an otherwise unstructured text.
    paratext = PARATEXT_RE.match(stripped)
    if paratext:
        kind = paratext.group("kind").lower()
        return 1, paratext.group("kind").upper(), kind

    match = LEGACY_PIPE_RE.match(stripped)
    if not match:
        return None

    title = _clean_title(match.group("title"))
    level = _legacy_heading_level(title)
    if level is None:
        return None
    return level, title, LEGACY_CONTENT_KIND


def _iter_page_spans(body: str) -> Iterable[_PageSpan]:
    cursor = 0
    found = False
    for match in PAGE_RE.finditer(body):
        found = True
        yield _PageSpan(
            start=cursor,
            end=match.start(),
            volume=int(match.group("volume")),
            page=int(match.group("page")),
            side=match.group("side"),
        )
        cursor = match.end()
    if cursor < len(body) or not found:
        yield _PageSpan(start=cursor, end=len(body), volume=None, page=None, side=None)


def _line_offsets(text: str, start: int, end: int) -> Iterable[tuple[int, int, str]]:
    cursor = start
    while cursor < end:
        newline = text.find("\n", cursor, end)
        line_end = end if newline == -1 else newline + 1
        yield cursor, line_end, text[cursor:line_end]
        cursor = line_end


def _update_section_stack(stack: list[str], level: int, title: str) -> None:
    while len(stack) >= level:
        stack.pop()
    while len(stack) < level - 1:
        stack.append("")
    stack.append(title)


def _structural_spans(
    body: str,
    page_span: _PageSpan,
    section_stack: list[str],
    current_kind: str,
) -> tuple[list[_StructuralSpan], str]:
    spans: list[_StructuralSpan] = []
    block_start: int | None = None
    block_section: tuple[str, ...] = tuple(section_stack)
    block_kind = current_kind

    def flush(end: int) -> None:
        nonlocal block_start
        if block_start is not None and end > block_start:
            spans.append(
                _StructuralSpan(
                    start=block_start,
                    end=end,
                    section_path=block_section,
                    content_kind=block_kind,
                )
            )
        block_start = None

    for line_start, line_end, line in _line_offsets(body, page_span.start, page_span.end):
        header = _parse_header(line)
        is_paragraph = line.startswith("# ") and not line.startswith("### ")

        if header is not None:
            flush(line_start)
            level, title, current_kind = header
            _update_section_stack(section_stack, level, title)
            block_start = line_start
            block_section = tuple(section_stack)
            block_kind = current_kind
        elif is_paragraph:
            flush(line_start)
            block_start = line_start
            block_section = tuple(section_stack)
            block_kind = current_kind
        elif block_start is None:
            block_start = line_start
            block_section = tuple(section_stack)
            block_kind = current_kind

        if line_end == page_span.end:
            flush(line_end)

    if page_span.start == page_span.end:
        return spans, current_kind
    if block_start is not None:
        flush(page_span.end)
    return spans, current_kind


def _split_span(body: str, span: _StructuralSpan, max_chars: int) -> list[_StructuralSpan]:
    if span.end - span.start <= max_chars:
        return [span]

    output: list[_StructuralSpan] = []
    cursor = span.start
    while cursor < span.end:
        hard_end = min(cursor + max_chars, span.end)
        if hard_end < span.end:
            window = body[cursor:hard_end]
            split_at = max(window.rfind("\n"), window.rfind(" "))
            if split_at >= int(max_chars * 0.6):
                hard_end = cursor + split_at + 1
        output.append(
            _StructuralSpan(
                start=cursor,
                end=hard_end,
                section_path=span.section_path,
                content_kind=span.content_kind,
            )
        )
        cursor = hard_end
    return output


def _normalize_search_text(text: str) -> str:
    value = normalize_arabic(text)
    value = LEGACY_MILESTONE_RE.sub(" ", value)
    # Legacy "# |" paragraph lines leave isolated pipe tokens after the normal
    # OpenITI prefix stripper. Remove only isolated pipes from the search copy.
    value = re.sub(r"(?<!\S)\|(?!\S)", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _chunk_legacy_body(
    body: str, version_uri: str, max_chars: int
) -> tuple[OpenITIChunk, ...]:
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")

    chunks: list[OpenITIChunk] = []
    sequence_no = 0
    section_stack: list[str] = []
    current_kind = "main"

    for page_span in _iter_page_spans(body):
        spans, current_kind = _structural_spans(
            body, page_span, section_stack, current_kind
        )
        expanded: list[_StructuralSpan] = []
        for span in spans:
            expanded.extend(_split_span(body, span, max_chars))

        group: list[_StructuralSpan] = []
        group_size = 0

        def emit_group() -> None:
            nonlocal sequence_no, group, group_size
            if not group:
                return

            start = group[0].start
            end = group[-1].end
            raw_chunk = body[start:end]
            normalized = _normalize_search_text(raw_chunk)
            if normalized:
                text_hash = sha256_text(raw_chunk)
                chunk_id = sha256_text(f"{version_uri}\n{sequence_no}\n{text_hash}")
                section_path = tuple(item for item in group[0].section_path if item)
                chunks.append(
                    OpenITIChunk(
                        chunk_id=chunk_id,
                        sequence_no=sequence_no,
                        text_original=raw_chunk,
                        text_normalized=normalized,
                        text_hash=text_hash,
                        volume=page_span.volume,
                        page=page_span.page,
                        page_side=page_span.side,
                        section_path=section_path,
                        section_title=section_path[-1] if section_path else None,
                        content_kind=group[0].content_kind,
                        source_start=start,
                        source_end=end,
                    )
                )
                sequence_no += 1

            group = []
            group_size = 0

        for span in expanded:
            span_size = span.end - span.start
            same_context = (
                not group
                or (
                    group[-1].section_path == span.section_path
                    and group[-1].content_kind == span.content_kind
                    and group[-1].end == span.start
                )
            )
            if group and (not same_context or group_size + span_size > max_chars):
                emit_group()
            group.append(span)
            group_size += span_size
        emit_group()

    return tuple(chunks)


def apply_legacy_pipe_structure(
    document: OpenITIDocument, *, max_chars: int = 1800
) -> tuple[OpenITIDocument, dict[str, int | bool | str]]:
    """Derive conservative structure from legacy ``# |`` lines when necessary.

    Standard OpenITI headers always win.  If even one explicit ``### |`` header
    exists, this compatibility layer is not applied.
    """

    if EXPLICIT_SECTION_RE.search(document.body):
        return document, {
            "legacy_structure_applied": False,
            "legacy_heading_candidates": 0,
            "legacy_inferred_chunks": 0,
            "structure_provenance": "openiti_explicit",
        }

    heading_candidates = sum(
        1 for line in document.body.splitlines() if _parse_header(line) is not None
    )
    if heading_candidates == 0:
        return document, {
            "legacy_structure_applied": False,
            "legacy_heading_candidates": 0,
            "legacy_inferred_chunks": 0,
            "structure_provenance": "none",
        }

    chunks = _chunk_legacy_body(document.body, document.uri.version_uri, max_chars)
    inferred_chunks = sum(
        1 for chunk in chunks if chunk.content_kind == LEGACY_CONTENT_KIND
    )

    return replace(document, chunks=chunks), {
        "legacy_structure_applied": True,
        "legacy_heading_candidates": heading_candidates,
        "legacy_inferred_chunks": inferred_chunks,
        "structure_provenance": "legacy_pipe_inferred",
    }
