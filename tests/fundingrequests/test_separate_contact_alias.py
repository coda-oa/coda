import json

import pytest

from coda.contexts.fundingrequest.dto.import_dtos import (
    FundingRequestImportDto,
    FundingRequestImportListDto,
    PublicationImportDto,
    SeparateContactImportDto,
)
from coda.domain.publication import OpenAccessType


def _dto() -> FundingRequestImportDto:
    return FundingRequestImportDto(
        request_date="2025-03-19",
        publication=PublicationImportDto(
            title="My article",
            kind="article",
            eissn="2434-561X",
            open_access_type=OpenAccessType.Opt_in,
        ),
        separate_contact=SeparateContactImportDto(name="John Smith", email="j@example.com"),
    )


def test_import_accepts_corrected_spelling() -> None:
    parsed = FundingRequestImportListDto.model_validate(
        {"requests": [{**_dto().model_dump(mode="json")}]}
    )

    assert parsed.requests[0].separate_contact.name == "John Smith"


def test_import_accepts_legacy_misspelled_alias() -> None:
    data = _dto().model_dump(mode="json", by_alias=False)
    legacy = json.dumps({"requests": [data]}).replace('"separate_contact"', '"seperate_contact"')

    parsed = FundingRequestImportListDto.model_validate_json(legacy)

    assert parsed.requests[0].separate_contact.name == "John Smith"
    assert parsed.requests[0].separate_contact.email == "j@example.com"


def test_export_serializes_corrected_spelling() -> None:
    dumped = _dto().model_dump(mode="json", by_alias=True)

    assert "separate_contact" in dumped
    assert "seperate_contact" not in dumped


def test_contact_defaults_to_empty_when_absent() -> None:
    data = _dto().model_dump(mode="json")
    del data["separate_contact"]

    parsed = FundingRequestImportListDto.model_validate({"requests": [data]})

    assert parsed.requests[0].separate_contact == SeparateContactImportDto.default()


@pytest.mark.parametrize("spelling", ["separate_contact", "seperate_contact"])
def test_both_spellings_in_json_stream(spelling: str) -> None:
    raw = json.dumps(
        {
            "requests": [
                {
                    "request_date": "2025-03-19",
                    "publication": {
                        "title": "My article",
                        "kind": "article",
                        "eissn": "2434-561X",
                        "open_access_type": "Opt-in",
                    },
                    spelling: {"name": "A", "email": "a@b.c"},
                }
            ]
        }
    )

    parsed = FundingRequestImportListDto.model_validate_json(raw)

    assert parsed.requests[0].separate_contact.name == "A"
