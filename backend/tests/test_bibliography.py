from app.bibliography.catalog import get_work_bibliography


def test_bidayat_bibliography_is_explicitly_sourced() -> None:
    record = get_work_bibliography("0595IbnRushdHafid.BidayatMujtahid")

    assert record is not None
    assert record.title_ar == "بداية المجتهد ونهاية المقتصد"
    assert record.title_latin == "Bidāyat al-mujtahid wa-nihāyat al-muqtaṣid"
    assert record.verification_status == "VERIFIED_EXTERNAL_CATALOG"
    assert record.source_name == "BnF Catalogue général"
    assert record.source_record_id == "cb32268155q"
    assert record.scope == "work_identity_and_title_only"
    assert "edition" in (record.notes or "").lower()


def test_unknown_work_is_not_given_invented_metadata() -> None:
    assert get_work_bibliography("0000Unknown.UnknownWork") is None
