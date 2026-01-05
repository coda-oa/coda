import abc
from decimal import Decimal
from typing import Annotated, Any, Literal, Self, TypeVar

import pydantic
from pydantic import Field, ValidatorFunctionWrapHandler, WrapValidator

from coda.apps.dto import CodaBaseDto
from coda.domain.finance.costtypes import ContractCostType, CostType, PublicationCostType
from coda.domain.finance.invoice_positions import ItemType
from coda.domain.finance.taxable_money import CostBasis

ItemT = TypeVar("ItemT", bound=ItemType, covariant=True)
CostT = TypeVar("CostT", bound=CostType, covariant=True)

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
DecimalOrAll = Annotated[Decimal | Literal["all"], fallback(Decimal(0))]


class RelatedFundingRequest(CodaBaseDto):
    request_id: str = ""
    url: str = ""


class PublicationItemDto(CodaBaseDto):
    """DTO for publication item - mirrors domain PublicationItem."""

    type: Literal["publication"] = "publication"
    id: IntOrDefault = 0
    title: str = ""
    funding_request: RelatedFundingRequest = RelatedFundingRequest()
    cost_type: str = PublicationCostType.Publication_Charge.value


class FreeItemDto(CodaBaseDto):
    """DTO for free-form item - mirrors domain FreeItem."""

    type: Literal["free"] = "free"
    description: str = ""
    cost_type: str = PublicationCostType.Publication_Charge.value


class ContractItemDto(CodaBaseDto):
    """DTO for contract item - mirrors domain ContractItem."""

    type: Literal["contract"] = "contract"
    id: IntOrDefault = 0
    name: str = ""
    year: IntOrDefault = 0
    cost_type: str = ContractCostType.Publish.value


type ItemDto = PublicationItemDto | FreeItemDto | ContractItemDto


class FundingAssignmentDto(CodaBaseDto):
    funding_source_type: Literal["budget", "institution"] = "budget"
    funding_source: IntOrNone = None
    amount: DecimalOrAll = Field(default=Decimal(0))


class PositionDto(abc.ABC, CodaBaseDto):
    item: ItemDto = Field(discriminator="type")
    cost_amount: DecimalOrDefault = Decimal("0.00")
    tax_rate: DecimalOrDefault = Decimal(DEFAULT_TAX_RATE_PERCENTAGE)
    external_position_id: str = ""
    cost_basis_mode: CostBasis = CostBasis.net
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

    @property
    def type(self) -> str:
        return self.item.type


class PositionList(pydantic.BaseModel):
    positions: list[PositionDto] = pydantic.Field(default_factory=list)
