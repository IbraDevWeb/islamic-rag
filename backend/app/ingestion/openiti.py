from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

HEADER_SPLITTER = "#META#Header#End#"
PAGE_RE = re.compile(r"(?P<marker>(?:Page|Folio)V(?P<volume>\d+)P(?P<page>\d+)(?P<side>[AB])?)")
SECTION_RE = re.compile(r"^###\s+(?P<pipes>\|+)\s*(?P<title>.*)$")
PARATEXT_RE = re.compile(r"^###\s+\|(?P<kind>EDITOR|PARATEXT|APPENDIX)\|\s*$", re.IGNORECASE)
LEADING_DEATH_YEAR_RE = re.compile(r"^(?P<year>\d{4})")
ARABIC_DIACRITICS_RE = re.compile(
    "[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]"
)
OPENITI_LINE_PREFIX_RE = re.compile(
    r"(?m)^(?:###\s+\|(?:EDITOR|PARATEXT|APPENDIX)\|\s*|###\s+\|+\s*|#\s+|~~)"
)
MILESTONE_RE = re.compile(r"\bMilestone\d+\b")


@dataclass(frozen=True)
class OpenITIUri:
    author_uri: str
    work_uri: str
    version_uri: str
    version_id: str
    language_code: str | None


@dataclass(frozen=True)
class OpenITIChunk:
    chunk_id: str
    sequence_no: int
    text_original: str
    text_normalized: str
    text_hash: str
    volume: int | None
    page: int | None
    page_side: str | None
    section_path: tuple[str, ...]
    section_title: str | None
    content_kind: str
    source_start: int
    source_end: int


@dataclass(frozen=True)
class OpenITIDocument:
    uri: OpenITIUri
    header: str
    body: str
    text_sha256: str
    version_metadata_sha256: str
    book_metadata_sha256: str | None
    author_metadata_sha256: str | None
    version_metadata: dict[str, Any]
    book_metadata: dict[str, Any]
    author_metadata: dict[str, Any]
    author_name_display: str | None
    author_death_year_ah: int | None
    work_title_display: str | None
    work_genres: str | None
    quality_issues: tuple[str, ...]
    chunks: tuple[OpenITIChunk, ...]


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


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def load_openiti_yml_text(raw: str) -> dict[str, Any]:
    parsed = yaml.safe_load(raw) or {}
    if not isinstance(parsed, dict):
        raise ValueError("OpenITI YAML must contain a mapping at the top level")
    return _json_safe(parsed)


def load_openiti_yml(path: str | Path) -> tuple[dict[str, Any], str]:
    raw = Path(path).read_text(encoding="utf-8-sig")
    return load_openiti_yml_text(raw), sha256_text(raw)


def split_openiti_text(raw: str) -> tuple[str, str]:
    if HEADER_SPLITTER not in raw:
        raise ValueError(f"Missing OpenITI header splitter: {HEADER_SPLITTER}")
    header, body = raw.split(HEADER_SPLITTER, 1)
    return header + HEADER_SPLITTER, body


def parse_openiti_uri(version_uri: str) -> OpenITIUri:
    value = version_uri.strip()
    parts = value.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError(
            "Expected OpenITI version URI in Author.Work.Version form; "
            f"got {version_uri!r}"
        )
    author_uri, work_id, version_id = parts
    work_uri = f"{author_uri}.{work_id}"
    language_match = re.search(r"-([a-z]{3}\d+)$", version_id, flags=re.IGNORECASE)
    language_code = language_match.group(1).lower() if language_match else None
    return OpenITIUri(
        author_uri=author_uri,
        work_uri=work_uri,
        version_uri=value,
        version_id=version_id,
        language_code=language_code,
    )


_PLACEHOLDER_PREFIXES = (
    "permalink",
    "year-mon-da",
    "formalized issues",
    "the name of the",
    "a free running comment",
    "uris from althurayya",
    "uri of a book from openiti",
)
_PLACEHOLDER_EXACT = {
    "kitāb al-muʾallif",
    "risālaŧ al-muʾallif",
}


def is_placeholder_metadata_value(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    if normalized in _PLACEHOLDER_EXACT:
        return True
    if normalized.startswith(_PLACEHOLDER_PREFIXES):
        return True
    if "src@keyword" in normalized:
        return True
    return False


def _metadata_value(
    metadata: dict[str, Any], *keys: str, meaningful: bool = False
) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value is not None:
            text = str(value).strip()
            if text and (not meaningful or not is_placeholder_metadata_value(text)):
                return text
    return None


def _parse_death_year(author_metadata: dict[str, Any], author_uri: str) -> int | None:
    raw = _metadata_value(author_metadata, "30#AUTH#DIED###AH")
    if raw:
        match = re.match(r"^(\d{4})", raw)
        if match:
            return int(match.group(1))
    match = LEADING_DEATH_YEAR_RE.match(author_uri)
    return int(match.group("year")) if match else None


def _quality_issues(version_metadata: dict[str, Any]) -> tuple[str, ...]:
    raw = _metadata_value(version_metadata, "90#VERS#ISSUES###", meaningful=True)
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def strip_openiti_markup(text: str) -> str:
    cleaned = PAGE_RE.sub(" ", text)
    cleaned = MILESTONE_RE.sub(" ", cleaned)
    cleaned = OPENITI_LINE_PREFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"(?m)^###\s+\$+\s*", "", cleaned)
    return cleaned


def normalize_arabic(text: str) -> str:
    value = unicodedata.normalize("NFKC", strip_openiti_markup(text))
    value = ARABIC_DIACRITICS_RE.sub("", value)
    value = value.replace("ـ", "")
    value = re.sub("[ٱأإآ]", "ا", value)
    value = value.replace("ى", "ي")
    value = re.sub(r"\s+", " ", value).strip()
    return value


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


def _parse_section_header(line: str) -> tuple[int, str, str] | None:
    stripped = line.strip()
    paratext = PARATEXT_RE.match(stripped)
    if paratext:
        kind = paratext.group("kind").lower()
        return 1, paratext.group("kind").upper(), kind
    section = SECTION_RE.match(stripped)
    if not section:
        return None
    title = section.group("title").strip()
    return len(section.group("pipes")), title, "main"


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
        header = _parse_section_header(line)
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


def chunk_openiti_body(
    body: str, version_uri: str, max_chars: int = 1800
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
            normalized = normalize_arabic(raw_chunk)
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


def build_openiti_document(
    text_raw: str,
    version_yml_raw: str,
    book_yml_raw: str | None = None,
    author_yml_raw: str | None = None,
    *,
    max_chars: int = 1800,
) -> OpenITIDocument:
    version_metadata = load_openiti_yml_text(version_yml_raw)
    book_metadata = load_openiti_yml_text(book_yml_raw) if book_yml_raw else {}
    author_metadata = load_openiti_yml_text(author_yml_raw) if author_yml_raw else {}

    version_uri_value = _metadata_value(version_metadata, "00#VERS#URI######")
    if not version_uri_value:
        raise ValueError("Version YAML is missing 00#VERS#URI######")
    uri = parse_openiti_uri(version_uri_value)

    book_uri_value = _metadata_value(book_metadata, "00#BOOK#URI######")
    if book_uri_value and book_uri_value != uri.work_uri:
        raise ValueError(
            f"Book YAML URI {book_uri_value!r} does not match version work URI {uri.work_uri!r}"
        )
    author_uri_value = _metadata_value(author_metadata, "00#AUTH#URI######")
    if author_uri_value and author_uri_value != uri.author_uri:
        raise ValueError(
            f"Author YAML URI {author_uri_value!r} does not match version author URI {uri.author_uri!r}"
        )

    header, body = split_openiti_text(text_raw)
    chunks = chunk_openiti_body(body, uri.version_uri, max_chars=max_chars)
    if not chunks:
        raise ValueError("No textual chunks were produced from the OpenITI body")

    return OpenITIDocument(
        uri=uri,
        header=header,
        body=body,
        text_sha256=sha256_text(text_raw),
        version_metadata_sha256=sha256_text(version_yml_raw),
        book_metadata_sha256=sha256_text(book_yml_raw) if book_yml_raw else None,
        author_metadata_sha256=sha256_text(author_yml_raw) if author_yml_raw else None,
        version_metadata=version_metadata,
        book_metadata=book_metadata,
        author_metadata=author_metadata,
        author_name_display=_metadata_value(
            author_metadata, "10#AUTH#SHUHRA#AR", meaningful=True
        ),
        author_death_year_ah=_parse_death_year(author_metadata, uri.author_uri),
        work_title_display=_metadata_value(
            book_metadata,
            "10#BOOK#TITLEA#AR",
            "10#BOOK#TITLEB#AR",
            meaningful=True,
        ),
        work_genres=_metadata_value(
            book_metadata, "10#BOOK#GENRES###", meaningful=True
        ),
        quality_issues=_quality_issues(version_metadata),
        chunks=chunks,
    )


def document_summary(document: OpenITIDocument) -> dict[str, Any]:
    pages = {
        (chunk.volume, chunk.page, chunk.page_side)
        for chunk in document.chunks
        if chunk.page is not None
    }
    return {
        "version_uri": document.uri.version_uri,
        "author_uri": document.uri.author_uri,
        "work_uri": document.uri.work_uri,
        "language_code": document.uri.language_code,
        "chunks": len(document.chunks),
        "pages_with_explicit_markers": len(pages),
        "text_sha256": document.text_sha256,
        "quality_issues": list(document.quality_issues),
    }


def metadata_json(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)
