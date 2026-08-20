from app.ingestion.legacy_structure import (
    LEGACY_CONTENT_KIND,
    apply_legacy_pipe_structure,
)
from app.ingestion.openiti import build_openiti_document


VERSION_YML = "00#VERS#URI######: 0595IbnRushdHafid.BidayatMujtahid.Test0001-ara1\n"


def test_legacy_pipe_headings_are_derived_only_when_explicit_headers_are_absent():
    text = """######OpenITI#
#META#Header#End#

# | بسم الله الرحمن الرحيم
# تمهيد لا يحمل عنوانا بنيويا.
PageV01P001

# | كتاب الطهارة
# نص في الطهارة.
PageV01P002

# | الباب الثالث في معرفة شروط ms0067 جواز هذه الطهارة
# نص الباب وفيه ms0007 علامة مصدرية.
PageV01P003
"""

    document = build_openiti_document(text, VERSION_YML, max_chars=500)
    derived, stats = apply_legacy_pipe_structure(document, max_chars=500)

    assert stats["legacy_structure_applied"] is True
    assert stats["legacy_heading_candidates"] == 2
    assert stats["structure_provenance"] == "legacy_pipe_inferred"

    book_chunks = [chunk for chunk in derived.chunks if chunk.section_title == "كتاب الطهارة"]
    chapter_chunks = [
        chunk
        for chunk in derived.chunks
        if chunk.section_title == "الباب الثالث في معرفة شروط جواز هذه الطهارة"
    ]

    assert book_chunks
    assert chapter_chunks
    assert all(chunk.content_kind == LEGACY_CONTENT_KIND for chunk in book_chunks)
    assert all(chunk.content_kind == LEGACY_CONTENT_KIND for chunk in chapter_chunks)
    assert chapter_chunks[0].section_path == (
        "كتاب الطهارة",
        "الباب الثالث في معرفة شروط جواز هذه الطهارة",
    )
    assert "ms0067" not in chapter_chunks[0].section_title
    assert "ms0007" not in chapter_chunks[0].text_normalized


def test_explicit_openiti_headers_disable_legacy_inference():
    text = """######OpenITI#
#META#Header#End#

### | كتاب الصلاة
# نص صحيح البنية.
# | كتاب الطهارة
# يبقى هذا سطرا فقريا لأن النص يملك بنية OpenITI صريحة.
PageV01P001
"""

    document = build_openiti_document(text, VERSION_YML, max_chars=500)
    derived, stats = apply_legacy_pipe_structure(document, max_chars=500)

    assert derived == document
    assert stats["legacy_structure_applied"] is False
    assert stats["structure_provenance"] == "openiti_explicit"
