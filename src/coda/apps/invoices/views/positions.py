import abc
from decimal import Decimal
from typing import Annotated, Generic, Self, TypeVar

from pydantic import BeforeValidator

from coda.apps.contracts import services as contract_services
from coda.apps.dto import CodaBaseDto
from coda.contract import ContractId, ContractYear
from coda.invoice import ItemType
from coda.publication import PublicationId

T = TypeVar("T", bound=ItemType, covariant=True)


def try_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


Int = Annotated[int, BeforeValidator(int)]
IntOrNone = Annotated[int | None, BeforeValidator(try_int)]


class CommonPosition(abc.ABC, CodaBaseDto, Generic[T]):
    type: str
    cost_type: str
    cost_amount: Decimal
    tax_rate: Decimal

    @classmethod
    def from_request(cls, post_data: dict[str, str], prefix: str = "") -> Self:
        if prefix:
            post_data = {
                key.removeprefix(prefix): value
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
    request_id: IntOrNone
    url: str = ""


class PublicationPosition(CommonPosition[PublicationId]):
    type: str = "publication"
    id: Int
    title: str
    funding_request: RelatedFundingRequest

    def parse(self) -> PublicationId:
        return PublicationId(self.id)

    def parse_safe(self) -> PublicationId:
        return self.parse()


class FreePosition(CommonPosition[str]):
    type: str = "free"
    description: str

    def parse(self) -> str:
        return self.description

    def parse_safe(self) -> str:
        return self.description


class ContractPosition(CommonPosition[ContractYear]):
    type: str = "contract"
    id: Int
    name: str
    contract_year: int

    def parse(self) -> ContractYear:
        contract = contract_services.get_by_id(ContractId(self.id))
        return contract.in_year(self.contract_year)

    def parse_safe(self) -> ContractYear:
        contract = contract_services.get_by_id(ContractId(self.id))
        return contract.in_year_or_first(self.contract_year)


_position_type_registry: dict[str, type[CommonPosition[ItemType]]] = {
    "publication": PublicationPosition,
    "free": FreePosition,
    "contract": ContractPosition,
}


def get_position_type(type_name: str) -> type[CommonPosition[ItemType]]:
    return _position_type_registry[type_name]
