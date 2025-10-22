from dataclasses import dataclass
from decimal import Decimal

from coda.contexts.finance.dto.edit_position_dtos import (
    ContractPositionDto,
    FreePositionDto,
    PublicationPositionDto,
)
from coda.contexts.finance.services import invoice_parser
from coda.domain.finance.costtypes import ContractCostType, PublicationCostType
from coda.domain.finance.invoice_positions import AnyPosition


class UnsupportedPositionTypeError(Exception):
    """Raised when an unsupported position DTO type is encountered."""

    pass


DEFAULT_TAX_RATE_PERCENTAGE = 19


@dataclass
class PositionDetailDto:
    type: str = ""
    title: str = ""
    url: str = ""
    funding_source: int | None = None
    cost_type: str = PublicationCostType.Publication_Charge.value
    tax_rate: Decimal = Decimal(DEFAULT_TAX_RATE_PERCENTAGE)
    tax_amount: Decimal = Decimal("0.00")
    net_costs: Decimal = Decimal("0.00")

    @classmethod
    def to_position_detail_dto(cls, position: AnyPosition) -> "PositionDetailDto":
        return build_position_detail_dto(position)


def build_position_detail_dto(position: AnyPosition) -> PositionDetailDto:
    dto = invoice_parser.position_to_dto(position)

    if isinstance(dto, PublicationPositionDto):
        return _from_publication_dto(dto, position)
    if isinstance(dto, ContractPositionDto):
        return _from_contract_dto(dto, position)
    if isinstance(dto, FreePositionDto):
        return _from_free_dto(dto, position)
    raise UnsupportedPositionTypeError(
        f"Unsupported DTO type: {type(dto).__name__}. "
        f"Supported types: {[PublicationPositionDto.__name__, ContractPositionDto.__name__, FreePositionDto.__name__]}"
    )


def _from_publication_dto(
    dto: PublicationPositionDto, position: AnyPosition
) -> "PositionDetailDto":
    is_vat = dto.cost_type == PublicationCostType.Vat.value
    return PositionDetailDto(
        type=dto.type,
        title=dto.title,
        url=dto.funding_request.url,
        funding_source=dto.funding_source,
        cost_type=dto.cost_type,
        tax_rate=Decimal("0.00") if is_vat else dto.tax_rate,
        tax_amount=position.tax().amount,
        net_costs=position.net().amount,
    )


def _from_contract_dto(dto: ContractPositionDto, position: AnyPosition) -> "PositionDetailDto":
    is_vat = dto.cost_type == ContractCostType.Vat.value
    return PositionDetailDto(
        type=dto.type,
        title=dto.name,
        url=dto.contract_url(),
        funding_source=dto.funding_source,
        cost_type=dto.cost_type,
        tax_rate=Decimal("0.00") if is_vat else dto.tax_rate,
        tax_amount=position.tax().amount,
        net_costs=position.net().amount,
    )


def _from_free_dto(dto: FreePositionDto, position: AnyPosition) -> "PositionDetailDto":
    return PositionDetailDto(
        type=dto.type,
        title=dto.description,
        url="",
        funding_source=dto.funding_source,
        cost_type=dto.cost_type,
        tax_rate=dto.tax_rate,
        tax_amount=position.tax().amount,
        net_costs=position.net().amount,
    )
