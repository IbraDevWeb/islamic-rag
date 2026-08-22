from app.search.semantic import (
    build_embedding_passage,
    build_embedding_query,
    qdrant_point_id,
    semantic_chunk_fingerprint,
)


def test_embedding_text_uses_e5_query_and_passage_prefixes() -> None:
    passage = build_embedding_passage(
        "احكام قصر الصلاة للمسافر",
        ("كتاب الصلاة", "الباب الرابع في صلاة السفر"),
    )
    query = build_embedding_query("قصر الصلاة في السفر")

    assert passage.startswith("passage: كتاب الصلاة / الباب الرابع في صلاة السفر\n")
    assert query == "query: قصر الصلاة في السفر"


def test_qdrant_point_id_is_stable_and_uuid_shaped() -> None:
    chunk_id = "a" * 64
    first = qdrant_point_id(chunk_id)
    second = qdrant_point_id(chunk_id)

    assert first == second
    assert len(first) == 36


def test_semantic_chunk_fingerprint_changes_with_chunk_identity() -> None:
    first_rows = [
        {
            "chunk_id": "a" * 64,
            "text_hash": "b" * 64,
            "work_uri": "work",
            "version_uri": "version",
            "quality_status": "UNREVIEWED",
            "sequence_no": 1,
        }
    ]
    second_rows = [
        {
            **first_rows[0],
            "text_hash": "c" * 64,
        }
    ]

    assert semantic_chunk_fingerprint(first_rows) != semantic_chunk_fingerprint(second_rows)
