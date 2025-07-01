import abc
from decimal import Decimal
from typing import Annotated, Generic, Self, TypeVar

from pydantic import BeforeValidator

from coda.apps.contracts import repository as contract_services
from coda.apps.dto import CodaBaseDto
from coda.apps.publications.repositories import publication_repository
from coda.domain.contract import ContractId, ContractYear
from coda.domain.invoice import CostType, ItemType, Position
from coda.domain.publication import PublicationId

T = TypeVar("T", bound=ItemType, covariant=True)

DEFAULT_TAX_RATE_PERCENTAGE = 19


def try_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


Int = Annotated[int, BeforeValidator(int)]
IntOrNone = Annotated[int | None, BeforeValidator(try_int)]


class CommonPosition(abc.ABC, CodaBaseDto, Generic[T]):
    type: str
    funding_source: IntOrNone = None
    cost_type: str = CostType.Publication_Charge.value
    cost_amount: Decimal = Decimal("0.00")
    tax_rate: Decimal = Decimal(DEFAULT_TAX_RATE_PERCENTAGE)
    external_position_id: str = ""

    @classmethod
    @abc.abstractmethod
    def from_position(cls, position: Position[T]) -> "CommonPosition[T]":
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
    def parse(self) -> T:
        ...

    @abc.abstractmethod
    def parse_safe(self) -> T:
        ...


class RelatedFundingRequest(CodaBaseDto):
    request_id: str = ""
    url: str = ""


class PublicationPosition(CommonPosition[PublicationId]):
    type: str = "publication"
    id: Int
    title: str
    funding_request: RelatedFundingRequest = RelatedFundingRequest()

    @classmethod
    def from_position(cls, position: Position[PublicationId]) -> "PublicationPosition":
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


class FreePosition(CommonPosition[str]):
    type: str = "free"
    description: str

    @classmethod
    def from_position(cls, position: Position[str]) -> "FreePosition":
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


class ContractPosition(CommonPosition[ContractYear]):
    """DTO for a contract position already added to an invoice."""

    type: str = "contract"
    id: Int
    name: str
    year: int

    @classmethod
    def from_position(cls, position: Position[ContractYear]) -> "ContractPosition":
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


_position_type_registry: dict[str, type[CommonPosition[ItemType]]] = {
    "publication": PublicationPosition,
    "free": FreePosition,
    "contract": ContractPosition,
}

_item_type_to_position: dict[type[ItemType], type[CommonPosition[ItemType]]] = {
    PublicationId: PublicationPosition,
    ContractYear: ContractPosition,
    str: FreePosition,
}


def position_type_names() -> list[str]:
    return list(_position_type_registry.keys())


def get_position_type(type_name: str) -> type[CommonPosition[ItemType]]:
    return _position_type_registry[type_name]


def to_position_dto(p: Position[ItemType]) -> CommonPosition[ItemType]:
    return _item_type_to_position[type(p.item)].from_position(p)
