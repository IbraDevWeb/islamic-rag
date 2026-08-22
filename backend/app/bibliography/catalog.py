from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class BibliographicRecord:
    """Project-curated bibliographic identity with explicit external provenance.

    This record identifies a work. It does not assert that the cited catalogue
    record is the same physical/digital edition as an ingested OpenITI text.
    Edition-level provenance remains attached to the text version/source.
    """

    work_uri: str
    title_ar: str
    title_latin: str | None
    source_name: str
    source_url: str
    source_record_id: str | None
    verified_on: date
    verification_status: str = "VERIFIED_EXTERNAL_CATALOG"
    scope: str = "work_identity_and_title_only"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["verified_on"] = self.verified_on.isoformat()
        return payload


# Deliberately small and reviewed by hand. We do not derive display titles from
# OpenITI identifiers when OpenITI book metadata contains placeholders.
_CATALOG: dict[str, BibliographicRecord] = {
    "0595IbnRushdHafid.BidayatMujtahid": BibliographicRecord(
        work_uri="0595IbnRushdHafid.BidayatMujtahid",
        title_ar="بداية المجتهد ونهاية المقتصد",
        title_latin="Bidāyat al-mujtahid wa-nihāyat al-muqtaṣid",
        source_name="BnF Catalogue général",
        source_url="https://catalogue.bnf.fr/ark:/12148/cb32268155q",
        source_record_id="cb32268155q",
        verified_on=date(2026, 8, 22),
        notes=(
            "The BnF record verifies the work title/identity. It is not used "
            "to claim edition or pagination identity with the OpenITI version."
        ),
    )
}


def get_work_bibliography(work_uri: str) -> BibliographicRecord | None:
    return _CATALOG.get(work_uri)
