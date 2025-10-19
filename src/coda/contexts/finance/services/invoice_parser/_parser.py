from coda.apps.invoices.views.position_dtos.edit_position_dtos import (
    AnyPositionDto,
    CommonPositionDto,
    ContractPositionDto,
    FreePositionDto,
    PublicationPositionDto,
)
from coda.domain.contract import ContractYear
from coda.domain.invoice import AnyPosition, CostType, ItemType
from coda.domain.publication.publication import PublicationId


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
