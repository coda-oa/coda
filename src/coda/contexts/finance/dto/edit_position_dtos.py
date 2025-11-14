import abc
from decimal import Decimal
from typing import Annotated, Any, Generic, Self, TypeVar

import pydantic
from django.urls import reverse
from pydantic import Field, ValidatorFunctionWrapHandler, WrapValidator

from coda.apps.dto import CodaBaseDto
from coda.domain.contract import ContractYear
from coda.domain.finance.costtypes import ContractCostType, CostType, PublicationCostType
from coda.domain.finance.invoice_positions import ItemType
from coda.domain.publication import PublicationId

ItemT = TypeVar("ItemT", bound=ItemType, covariant=True)
CostT = TypeVar("CostT", bound=CostType, covariant=True)
type PositionDto = "PublicationPositionDto | ContractPositionDto | FreePositionDto"

DEFAULT_TAX_RATE_PERCENTAGE = 19


def fallback(v: Any) -> WrapValidator:
    def _handler(value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        try:
            return handler(value)
        except (TypeError, ValueError):
            return v

    return WrapValidator(_handler)


IntOrDefault = Annotated[int, fallback(0)]
DecimalOrDefault = Annotated[Decimal, fallback(Decimal(0))]
IntOrNone = Annotated[int | None, fallback(None)]


class FundingAssignmentDto(CodaBaseDto):
    funding_source: IntOrNone = None
    amount: DecimalOrDefault = Decimal(0)


class CommonPositionDto(abc.ABC, CodaBaseDto, Generic[ItemT, CostT]):
    type: str
    funding_source: IntOrNone = None
    cost_type: str = PublicationCostType.Publication_Charge.value
    cost_amount: DecimalOrDefault = Decimal("0.00")
    tax_rate: DecimalOrDefault = Decimal(DEFAULT_TAX_RATE_PERCENTAGE)
    external_position_id: str = ""
    funding_assignments: list[FundingAssignmentDto] = Field(default_factory=list)
    unassigned_costs: DecimalOrDefault = Decimal(0)

    @classmethod
    def from_request(cls, post_data: dict[str, str], prefix: str = "") -> Self:
        if prefix:
            post_data = {
                key.removeprefix(prefix).replace("-", "_"): value
                for key, value in post_data.items()
                if key.startswith(prefix)
            }

        return cls.model_validate(post_data)


class RelatedFundingRequest(CodaBaseDto):
    request_id: str = ""
    url: str = ""


class PublicationPositionDto(CommonPositionDto[PublicationId, PublicationCostType]):
    type: str = "publication"
    id: IntOrDefault = 0
    title: str = ""
    funding_request: RelatedFundingRequest = RelatedFundingRequest()


class FreePositionDto(CommonPositionDto[str, PublicationCostType]):
    type: str = "free"
    description: str = ""


class ContractPositionDto(CommonPositionDto[ContractYear, ContractCostType]):
    """DTO for a contract position already added to an invoice."""

    type: str = "contract"
    id: IntOrDefault = 0
    name: str = ""
    year: IntOrDefault = 0
    cost_type: str = ContractCostType.Publish.value

    def contract_url(self) -> str:
        url = reverse("contracts:detail", kwargs={"pk": self.id})
        return url


class PositionList(pydantic.BaseModel):
    positions: list[
        PublicationPositionDto | ContractPositionDto | FreePositionDto
    ] = pydantic.Field(default_factory=list)
