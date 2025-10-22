import abc
from collections.abc import Iterable
from decimal import Decimal
from typing import Annotated, Generic, Self, TypeVar

from django.urls import reverse
from pydantic import BeforeValidator

from coda.apps.dto import CodaBaseDto
from coda.domain.contract import ContractYear
from coda.domain.finance.costtypes import ContractCostType, CostType, PublicationCostType
from coda.domain.finance.invoice_positions import ItemType
from coda.domain.publication import PublicationId

ItemT = TypeVar("ItemT", bound=ItemType, covariant=True)
CostT = TypeVar("CostT", bound=CostType, covariant=True)
type AnyPositionDto = "CommonPositionDto[ItemType, CostType]"
type PositionDtos = Iterable["CommonPositionDto[ItemType, CostType]"]

DEFAULT_TAX_RATE_PERCENTAGE = 19


def try_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


Int = Annotated[int, BeforeValidator(int)]
IntOrNone = Annotated[int | None, BeforeValidator(try_int)]


class CommonPositionDto(abc.ABC, CodaBaseDto, Generic[ItemT, CostT]):
    type: str
    funding_source: IntOrNone = None
    cost_type: str = PublicationCostType.Publication_Charge.value
    cost_amount: Decimal = Decimal("0.00")
    tax_rate: Decimal = Decimal(DEFAULT_TAX_RATE_PERCENTAGE)
    external_position_id: str = ""

    @classmethod
    def from_request(cls, post_data: dict[str, str], prefix: str = "") -> Self:
        if prefix:
            post_data = {
                key.removeprefix(prefix).replace("-", "_"): value
                for key, value in post_data.items()
                if key.startswith(prefix)
            }

        return cls(**post_data)


class RelatedFundingRequest(CodaBaseDto):
    request_id: str = ""
    url: str = ""


class PublicationPositionDto(CommonPositionDto[PublicationId, PublicationCostType]):
    type: str = "publication"
    id: Int
    title: str
    funding_request: RelatedFundingRequest = RelatedFundingRequest()


class FreePositionDto(CommonPositionDto[str, PublicationCostType]):
    type: str = "free"
    description: str


class ContractPositionDto(CommonPositionDto[ContractYear, ContractCostType]):
    """DTO for a contract position already added to an invoice."""

    type: str = "contract"
    id: Int
    name: str
    year: int
    cost_type: str = ContractCostType.Publish.value

    def contract_url(self) -> str:
        url = reverse("contracts:detail", kwargs={"pk": self.id})
        return url
