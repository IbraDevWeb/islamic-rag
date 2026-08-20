import hashlib

from app.ingestion.openiti import build_openiti_document
from app.ingestion.openiti_yml import as_strict_yaml_input, parse_openiti_yml_text


REALISTIC_VERSION_YML = """00#VERS#CLENGTH##: 1257663
00#VERS#LENGTH###: 305252
00#VERS#URI######: 0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1
90#VERS#COMMENT##: All paratextual elements
    removed by HRH and MGR (OpenITI Clean operation, 2023)
    Link to the text file as it was before it was cleaned:
    https://raw.githubusercontent.com/OpenITI/0600AH/pre-clean/example
90#VERS#ISSUES###: PRIMARY_VERSION, CLEANED_VERSION
"""

SAMPLE_TEXT = """######OpenITI#
#META#Header#End#
# نص تجريبي.
PageV01P001
"""


def test_openiti_yml_parser_accepts_colons_in_continuation_lines():
    metadata = parse_openiti_yml_text(REALISTIC_VERSION_YML)

    assert metadata["00#VERS#URI######"] == (
        "0595IbnRushdHafid.BidayatMujtahid.JK000222-ara1"
    )
    assert "cleaned:" in metadata["90#VERS#COMMENT##"]
    assert "https://raw.githubusercontent.com" in metadata["90#VERS#COMMENT##"]
    assert metadata["90#VERS#ISSUES###"] == "PRIMARY_VERSION, CLEANED_VERSION"


def test_realistic_openiti_yml_can_build_document_without_changing_raw_hash():
    strict_input = as_strict_yaml_input(REALISTIC_VERSION_YML)
    document = build_openiti_document(SAMPLE_TEXT, strict_input, max_chars=500)

    assert document.uri.version_id == "JK000222-ara1"
    assert document.quality_issues == ("PRIMARY_VERSION", "CLEANED_VERSION")
    assert hashlib.sha256(REALISTIC_VERSION_YML.encode("utf-8")).hexdigest() != document.version_metadata_sha256
    # The CLI restores the raw source hash after parsing; this assertion ensures
    # the adapter is actually transforming only the parser input, not the source file.
