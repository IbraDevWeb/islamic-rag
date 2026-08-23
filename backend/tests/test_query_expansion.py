import pytest

from app.search.query_expansion import QUERY_EXPANSION_ID, expand_query_variants


def test_qirad_mudaraba_alias_expands_both_directions() -> None:
    assert expand_query_variants("المضاربة") == ("المضاربة", "القراض")
    assert expand_query_variants("القراض") == ("القراض", "المضاربة")


def test_query_expansion_preserves_unmapped_query() -> None:
    assert expand_query_variants("الصلاة في السفر") == ("الصلاة في السفر",)


def test_query_expansion_replaces_alias_inside_longer_query() -> None:
    assert expand_query_variants("أحكام المضاربة") == (
        "احكام المضاربة",
        "احكام القراض",
    )


def test_query_expansion_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        expand_query_variants("   ")


def test_query_expansion_id_is_versioned() -> None:
    assert QUERY_EXPANSION_ID == "curated_fiqh_aliases_v1"
