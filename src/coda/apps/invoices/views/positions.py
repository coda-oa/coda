import abc
from collections.abc import Iterable
from decimal import Decimal
from typing import Annotated, Generic, Self, TypeVar

from pydantic import BeforeValidator

from coda.apps.contracts import repository as contract_services
from coda.apps.dto import CodaBaseDto
from coda.apps.publications.repositories import publication_repository
from coda.domain.contract import ContractId, ContractYear
from coda.domain.invoice import (
    AnyPosition,
    CommonPosition,
    ContractCostType,
    ContractPosition,
    CostType,
    FundingSourceId,
    ItemType,
    Position,
    PublicationCostType,
    TaxRate,
)
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
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
    @abc.abstractmethod
    def from_position(
        cls, position: CommonPosition[ItemT, CostT]
    ) -> "CommonPositionDto[ItemT, CostT]":
        ...

    @classmethod
    def from_request(cls, post_data: dict[str, str], prefix: str = "") -> Self:
        if prefix:
            post_data = {
                key.removeprefix(prefix).replace("-", "_"): value
                for key, value in post_data.items()
                if key.startswith(prefix)
            }

        return cls(**post_data)

    @abc.abstractmethod
    def parse(self) -> ItemT:
        ...

    @abc.abstractmethod
    def parse_safe(self) -> ItemT:
        ...

    @abc.abstractmethod
    def to_position(
        self, currency: Currency, *, parse_safe: bool = False
    ) -> CommonPosition[ItemT, CostT]:
        ...


class RelatedFundingRequest(CodaBaseDto):
    request_id: str = ""
    url: str = ""


class PublicationPositionDto(CommonPositionDto[PublicationId, PublicationCostType]):
    type: str = "publication"
    id: Int
    title: str
    funding_request: RelatedFundingRequest = RelatedFundingRequest()

    @classmethod
    def from_position(
        cls, position: CommonPosition[PublicationId, PublicationCostType]
    ) -> "PublicationPositionDto":
        publication = publication_repository.get_by_id(position.item)

        return cls(
            id=publication.id,
            title=publication.title,
            funding_source=position.funding_source,
            cost_type=position.cost_type,
            cost_amount=position.cost.amount,
            tax_rate=position.tax_rate.percentage(),
            external_position_id=position.external_position_id,
        )

    def parse(self) -> PublicationId:
        return PublicationId(self.id)

    def parse_safe(self) -> PublicationId:
        return self.parse()

    def to_position(
        self, currency: Currency, *, parse_safe: bool = False
    ) -> Position[PublicationId]:
        return Position(
            item=self.parse(),
            cost_type=PublicationCostType(self.cost_type),
            cost=Money(self.cost_amount, currency),
            tax_rate=TaxRate.from_percentage(self.tax_rate),
            funding_source=FundingSourceId(self.funding_source) if self.funding_source else None,
            external_position_id=self.external_position_id,
        )


class FreePositionDto(CommonPositionDto[str, PublicationCostType]):
    type: str = "free"
    description: str

    @classmethod
    def from_position(cls, position: CommonPosition[str, PublicationCostType]) -> "FreePositionDto":
        return cls(
            description=position.item,
            funding_source=position.funding_source,
            cost_amount=position.cost.amount,
            cost_type=position.cost_type,
            tax_rate=position.tax_rate.percentage(),
            external_position_id=position.external_position_id,
        )

    def parse(self) -> str:
        return self.description

    def parse_safe(self) -> str:
        return self.description

    def to_position(self, currency: Currency, *, parse_safe: bool = False) -> Position[str]:
        return Position(
            item=self.parse(),
            cost_type=PublicationCostType(self.cost_type),
            cost=Money(self.cost_amount, currency),
            tax_rate=TaxRate.from_percentage(self.tax_rate),
            funding_source=FundingSourceId(self.funding_source) if self.funding_source else None,
            external_position_id=self.external_position_id,
        )


class ContractPositionDto(CommonPositionDto[ContractYear, ContractCostType]):
    """DTO for a contract position already added to an invoice."""

    type: str = "contract"
    id: Int
    name: str
    year: int

    @classmethod
    def from_position(
        cls, position: CommonPosition[ContractYear, ContractCostType]
    ) -> "ContractPositionDto":
        if not position.item.contract_id:
            raise ValueError("Contract ID is required for ContractPosition")

        contract = contract_services.get_by_id(position.item.contract_id)

        return cls(
            id=contract.id,
            name=contract.name,
            funding_source=position.funding_source,
            year=position.item.year,
            cost_amount=position.cost.amount,
            cost_type=position.cost_type,
            tax_rate=position.tax_rate.percentage(),
            external_position_id=position.external_position_id,
        )

    def parse(self) -> ContractYear:
        contract = contract_services.get_by_id(ContractId(self.id))
        return contract.in_year(self.year)

    def parse_safe(self) -> ContractYear:
        contract = contract_services.get_by_id(ContractId(self.id))
        return contract.in_year_or_first(self.year)

    def to_position(self, currency: Currency, *, parse_safe: bool = False) -> ContractPosition:
        if parse_safe:
            item = self.parse_safe()
        else:
            item = self.parse()

        return ContractPosition(
            item=item,
            cost_type=ContractCostType(self.cost_type),
            cost=Money(self.cost_amount, currency),
            tax_rate=TaxRate.from_percentage(self.tax_rate),
            funding_source=FundingSourceId(self.funding_source) if self.funding_source else None,
            external_position_id=self.external_position_id,
        )


_position_type_registry: dict[str, type[CommonPositionDto[ItemType, CostType]]] = {
    "publication": PublicationPositionDto,
    "free": FreePositionDto,
    "contract": ContractPositionDto,
}

_item_type_to_position: dict[type[ItemType], type[CommonPositionDto[ItemType, CostType]]] = {
    PublicationId: PublicationPositionDto,
    ContractYear: ContractPositionDto,
    str: FreePositionDto,
}


def position_type_names() -> list[str]:
    return list(_position_type_registry.keys())


def get_position_type(type_name: str) -> type[AnyPositionDto]:
    return _position_type_registry[type_name]


def to_position_dto(p: AnyPosition) -> AnyPositionDto:
    return _item_type_to_position[type(p.item)].from_position(p)
