"""Typed filter criteria persisted with funding request CSV exports and openCost reports.

``ExportFiltersDto`` is the single schema for the ``filters`` JSON field on
``FundingRequestCSVExport`` and ``OpenCostReport``. It replaces the former
hand-written serialization into (and re-parsing out of) a comma-joined
string dictionary with one declarative model:

- ``from_form_data`` maps validated form input into the DTO.
- ``to_storage`` produces the JSON-serializable dict written to the database.
- ``model_validate`` reads persisted rows back, accepting the legacy
  comma-joined / alias formats written before this model existed.
- ``to_params`` yields the query-layer search parameters.
"""

from datetime import date
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import AliasChoices, BeforeValidator, ConfigDict, Field
from coda.apps.dto import CodaBaseDto
from coda.apps.fundingrequests.fundingrequest_query import (
    FundingRequestSearchParams,
    PaymentStatus,
    PublicationEntityType,
)
from coda.domain.date import DateRange
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import DecimalSeparator
from coda.domain.publication import OpenAccessType

if TYPE_CHECKING:
    from coda.apps.exports.services.filter_form import FilterCleanedData


def _csv_list(value: Any) -> Any:
    """Split legacy rows that stored multi values as comma-joined strings."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class ExportFiltersDto(CodaBaseDto):
    """Filter criteria of a funding request export/report, typed and validated.

    Field declaration order doubles as the applied-filters display order.
    Field titles serve both the applied-filters list and form error lines.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    period_start: date | None = Field(default=None, title="Period Start")
    period_end: date | None = Field(default=None, title="Period End")
    processing_status: Annotated[list[ReviewResult] | None, BeforeValidator(_csv_list)] = Field(
        default=None, title="Processing Status"
    )
    payment_methods: Annotated[list[PaymentMethod] | None, BeforeValidator(_csv_list)] = Field(
        default=None, title="Payment Methods"
    )
    open_access_type: Annotated[list[OpenAccessType] | None, BeforeValidator(_csv_list)] = Field(
        default=None, title="Open Access Type"
    )
    publication_states: Annotated[list[str] | None, BeforeValidator(_csv_list)] = Field(
        default=None, title="Publication States"
    )
    labels: Annotated[list[int] | None, BeforeValidator(_csv_list)] = Field(
        default=None, title="Labels"
    )
    exclude_labels: Annotated[list[int] | None, BeforeValidator(_csv_list)] = Field(
        default=None, title="Excluded Labels"
    )
    payment_status: Annotated[list[PaymentStatus] | None, BeforeValidator(_csv_list)] = Field(
        default=None, title="Payment Status"
    )
    publication_type: PublicationEntityType | None = Field(
        default=None,
        title="Publication Type",
        validation_alias=AliasChoices("publication_type", "entity_type"),
    )
    contract_name: int | None = Field(
        default=None,
        title="Contracts",
        validation_alias=AliasChoices("contract_name", "contract"),
    )
    funding_source: FundingSourceId | None = Field(default=None, title="Funding Source")
    decimal_separator: DecimalSeparator | None = Field(default=None, title="Decimal Separator")
    search_term: str | None = Field(default=None, title="Search Term")

    @classmethod
    def from_form_data(cls, data: "FilterCleanedData") -> "ExportFiltersDto":
        """Build the DTO from validated ``FundingRequestFilterForm`` data."""
        contract = data["contract_name"]
        funding_source = data["funding_source"]
        return cls(
            period_start=data["period_start"],
            period_end=data["period_end"],
            processing_status=data["processing_status"] or None,
            payment_status=data["payment_status"] or None,
            payment_methods=data["payment_methods"] or None,
            open_access_type=data["open_access_type"] or None,
            publication_states=data["publication_states"] or None,
            publication_type=(
                PublicationEntityType(data["publication_type"])
                if data["publication_type"]
                else None
            ),
            labels=[label.pk for label in data["labels"]] or None,
            exclude_labels=[label.pk for label in data["exclude_labels"]] or None,
            funding_source=(
                FundingSourceId(funding_source.pk) if funding_source is not None else None
            ),
            contract_name=contract.pk if contract is not None else None,
            decimal_separator=data["decimal_separator"],
            search_term=data["search_term"] or None,
        )

    def to_storage(self) -> dict[str, Any]:
        """Serialize to the dict persisted in the JSON field.

        Keys are omitted while the filter is unset, so persisted rows only
        carry the criteria that were actually applied.
        """
        dumped: dict[str, Any] = self.model_dump(mode="json", exclude_defaults=True)
        return dumped

    def to_params(self) -> FundingRequestSearchParams:
        """Translate into the query-layer search parameters."""
        date_range = (
            DateRange(self.period_start, self.period_end)
            if self.period_start is not None and self.period_end is not None
            else None
        )
        return FundingRequestSearchParams(
            date_range=date_range,
            review_results=self.processing_status or None,
            payment_statuses=self.payment_status or None,
            labels=self.labels or None,
            exclude_labels=self.exclude_labels or None,
            payment_methods=self.payment_methods or None,
            open_access_types=self.open_access_type or None,
            publication_states=self.publication_states or None,
            entity_type=self.publication_type or PublicationEntityType.All,
            search_term=self.search_term or "",
            contract_id=self.contract_name,
            funding_source=self.funding_source,
            decimal_separator=self.decimal_separator.value if self.decimal_separator else ".",
        )
