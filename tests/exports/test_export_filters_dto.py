from datetime import date

from coda.apps.fundingrequests.fundingrequest_query import PublicationEntityType, ReviewResult
from coda.contexts.exports.dto.filters import ExportFiltersDto
from coda.domain.date import DateRange
from coda.domain.finance.invoice import FundingSourceId


def test__legacy_row__validating__decodes_comma_strings_and_legacy_keys() -> None:
    legacy_row = {
        "period_start": "2024-01-01",
        "period_end": "2024-12-31",
        "processing_status": "approved,rejected",
        "labels": "1,2",
        "contract": "5",
        "entity_type": "article",
        "decimal_separator": ",",
        "obsolete_key": "ignored",
    }

    params = ExportFiltersDto.model_validate(legacy_row).to_params()

    assert params.date_range == DateRange(date(2024, 1, 1), date(2024, 12, 31))
    assert params.review_results == [ReviewResult.Approved, ReviewResult.Rejected]
    assert params.labels == [1, 2]
    assert params.contract_id == 5
    assert params.entity_type == PublicationEntityType.Article
    assert params.decimal_separator == ","


def test__storage_round_trip__revalidating__is_stable() -> None:
    dto = ExportFiltersDto(
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31),
        labels=[1, 2],
        funding_source=FundingSourceId(3),
    )

    storage = dto.to_storage()
    reloaded = ExportFiltersDto.model_validate(storage)

    assert storage == {
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
        "labels": [1, 2],
        "funding_source": 3,
    }
    assert reloaded == dto
