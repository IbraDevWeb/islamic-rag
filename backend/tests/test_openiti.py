import hashlib

import pytest

from app.ingestion.openiti import (
    build_openiti_document,
    normalize_arabic,
    parse_openiti_uri,
)


SAMPLE_TEXT = """######OpenITI#
#META# 000#VERS#CLENGTH##: 123
#META#Header#End#

### | كتاب الصلاة
# هٰذَا نَصُّ الصَّفْحَةِ الأُولَى
~~ وتتمة الفقرة.
PageV01P001

# ما زال في كتاب الصلاة.
### || باب السفر
# نص الصفحة الثانية.
PageV01P002

# نص بعد آخر علامة صفحة.
"""

VERSION_YML = """00#VERS#URI######: 0595IbnRushdHafid.BidayatMujtahid.Shamela0000001-ara1
90#VERS#ISSUES###: PAGINATION, FOOTNOTES
"""

BOOK_YML = """00#BOOK#URI######: 0595IbnRushdHafid.BidayatMujtahid
10#BOOK#GENRES###: FIQH@fiqh
10#BOOK#TITLEA#AR: Bidāyat al-mujtahid
"""

AUTHOR_YML = """00#AUTH#URI######: 0595IbnRushdHafid
10#AUTH#SHUHRA#AR: Ibn Rušd al-Ḥafīd
30#AUTH#DIED###AH: 0595-XX-XX
"""


def test_parse_version_uri():
    uri = parse_openiti_uri(
        "0595IbnRushdHafid.BidayatMujtahid.Shamela0000001-ara1"
    )
    assert uri.author_uri == "0595IbnRushdHafid"
    assert uri.work_uri == "0595IbnRushdHafid.BidayatMujtahid"
    assert uri.version_id == "Shamela0000001-ara1"
    assert uri.language_code == "ara1"


def test_build_document_preserves_exact_chunk_slices_and_page_markers():
    document = build_openiti_document(
        SAMPLE_TEXT,
        VERSION_YML,
        BOOK_YML,
        AUTHOR_YML,
        max_chars=500,
    )

    assert document.author_death_year_ah == 595
    assert document.author_name_display == "Ibn Rušd al-Ḥafīd"
    assert document.work_title_display == "Bidāyat al-mujtahid"
    assert document.quality_issues == ("PAGINATION", "FOOTNOTES")

    page_one = [chunk for chunk in document.chunks if chunk.page == 1]
    page_two = [chunk for chunk in document.chunks if chunk.page == 2]
    trailing = [chunk for chunk in document.chunks if chunk.page is None]

    assert page_one
    assert page_two
    assert trailing
    assert any(chunk.section_title == "كتاب الصلاة" for chunk in page_one)
    assert any(chunk.section_title == "باب السفر" for chunk in page_two)

    for chunk in document.chunks:
        assert document.body[chunk.source_start : chunk.source_end] == chunk.text_original
        assert hashlib.sha256(chunk.text_original.encode("utf-8")).hexdigest() == chunk.text_hash
        assert "PageV" not in chunk.text_original


def test_page_marker_is_end_of_corresponding_page():
    document = build_openiti_document(
        SAMPLE_TEXT,
        VERSION_YML,
        BOOK_YML,
        AUTHOR_YML,
        max_chars=500,
    )
    page_one_text = " ".join(
        chunk.text_normalized for chunk in document.chunks if chunk.page == 1
    )
    page_two_text = " ".join(
        chunk.text_normalized for chunk in document.chunks if chunk.page == 2
    )
    trailing_text = " ".join(
        chunk.text_normalized for chunk in document.chunks if chunk.page is None
    )

    assert "الصفحة الاولي" in page_one_text
    assert "نص الصفحة الثانية" in page_two_text
    assert "بعد اخر علامة صفحة" in trailing_text


def test_normalization_does_not_change_original_input():
    original = "# أَحْمَدُ إلى هٰذَا النَّصِ"
    before = original
    normalized = normalize_arabic(original)
    assert original == before
    assert normalized == "احمد الي هذا النص"


def test_mismatched_book_metadata_is_rejected():
    wrong_book = "00#BOOK#URI######: 0310Tabari.OtherBook\n"
    with pytest.raises(ValueError, match="does not match"):
        build_openiti_document(SAMPLE_TEXT, VERSION_YML, wrong_book, AUTHOR_YML)


def test_template_placeholders_are_not_promoted_to_display_metadata():
    template_book = """00#BOOK#URI######: 0595IbnRushdHafid.BidayatMujtahid
10#BOOK#GENRES###: src@keyword, src@keyword
10#BOOK#TITLEA#AR: Kitāb al-Muʾallif
10#BOOK#TITLEB#AR: Risālaŧ al-Muʾallif
"""
    template_version = """00#VERS#URI######: 0595IbnRushdHafid.BidayatMujtahid.Shamela0000001-ara1
90#VERS#ISSUES###: formalized issues, separated with commas
"""
    document = build_openiti_document(
        SAMPLE_TEXT, template_version, template_book, AUTHOR_YML, max_chars=500
    )
    assert document.work_title_display is None
    assert document.work_genres is None
    assert document.quality_issues == ()
