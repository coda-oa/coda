"""Tests for the enrich_from_ror function."""

from unittest.mock import patch


from coda.contexts.fundingrequest.services.funder_resolution.enrichment import enrich_from_ror
from coda.contexts.fundingrequest.services.funder_resolution.ror_client.ror_client import (
    RORRecord,
)
from coda.domain.fundingrequest import FunderRecord
from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId


def _ror_record(
    *,
    id: str = "https://ror.org/04pz7b180",
    name: str = "Updated Org",
    fundref: str | None = None,
) -> RORRecord:
    ext_ids: dict[str, list[str]] = {}
    if fundref:
        ext_ids["fundref"] = [fundref]
    return RORRecord(id=id, name=name, external_ids=ext_ids)


def test__enrich_from_ror__given_matching_record__updates_name_and_links() -> None:
    funder = FunderRecord(
        name="Old Name",
        links=(Ror("https://ror.org/04pz7b180"),),
    )
    record = _ror_record(name="New Name", fundref="501100002347")
    api_result = {"https://ror.org/04pz7b180": record}

    result = enrich_from_ror(funder, api_result)

    assert result.name == "New Name"
    assert Ror("https://ror.org/04pz7b180") in result.links
    assert CrossrefId("501100002347") in result.links


def test__enrich_from_ror__given_no_matching_record__returns_unchanged() -> None:
    funder = FunderRecord(
        name="Original Name",
        links=(Ror("https://ror.org/04pz7b180"),),
    )
    api_result: dict[str, RORRecord] = {}

    result = enrich_from_ror(funder, api_result)

    assert result is funder
    assert result.name == "Original Name"


def test__enrich_from_ror__given_record_conversion_error__returns_unchanged() -> None:
    funder = FunderRecord(
        name="Original Name",
        links=(Ror("https://ror.org/04pz7b180"),),
    )
    record = _ror_record()
    api_result = {"https://ror.org/04pz7b180": record}

    with patch.object(RORRecord, "to_links", side_effect=ValueError("bad data")):
        result = enrich_from_ror(funder, api_result)

    assert result is funder
    assert result.name == "Original Name"


def test__enrich_from_ror__given_multiple_records__uses_first_match() -> None:
    funder = FunderRecord(
        name="Old Name",
        links=(
            Ror("https://ror.org/04pz7b180"),
            CrossrefId("501100002347"),
        ),
    )
    record_ror = _ror_record(id="https://ror.org/04pz7b180", name="From ROR")
    record_crossref = _ror_record(id="https://ror.org/0134qgb15", name="From Crossref")
    api_result = {
        "https://ror.org/04pz7b180": record_ror,
        "501100002347": record_crossref,
    }

    result = enrich_from_ror(funder, api_result)

    assert result.name == "From ROR"
