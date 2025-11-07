from decimal import Decimal

from typing_extensions import TypeIs

from coda.apps.fundingrequests import repository
from coda.apps.publications.repositories import publication_repository
from coda.contexts.finance.dto.edit_position_dtos import (
    PositionDto,
    FundingAssignmentDto,
    PublicationPositionDto,
    RelatedFundingRequest,
)
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.finance.invoice_positions import Position, PositionItemType, PublicationItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.domain.publication.publication import PublicationId


def parse_item(position: PublicationPositionDto, *, parse_safe: bool = True) -> PublicationId:
    _ = parse_safe
    return PublicationId(position.id)


def parse_cost_type(position: PublicationPositionDto) -> PublicationCostType:
    return PublicationCostType(position.cost_type)


def to_position(
    position: PublicationPositionDto, currency: Currency, *, parse_safe: bool = False
) -> Position:
    _position = invoice_positions.create(
        item=PublicationItem(
            parse_item(position, parse_safe=parse_safe),
            cost_type=parse_cost_type(position),
        ),
        cost=Money(position.cost_amount, currency),
        tax_rate=TaxRate.from_percentage(position.tax_rate),
        external_position_id=position.external_position_id,
        funding_source=FundingSourceId(position.funding_source)
        if position.funding_source
        else None,
    )
    for f in position.funding_assignments:
        fid = FundingSourceId(f.funding_source) if f.funding_source else None
        _position.assign_funding(fid, f.amount)

    return _position


def position_to_dto(position: Position) -> PublicationPositionDto:
    assert _is_publicationitem(position.item)
    publication = publication_repository.get_by_id(position.item.item)
    assert publication.id is not None

    is_vat = position.item.cost_type == PublicationCostType.Vat

    funding_request = RelatedFundingRequest()
    reference = repository.find_reference_by_publication(publication.id)
    if reference:
        funding_request = RelatedFundingRequest(request_id=reference.request_id, url=reference.url)

    return PublicationPositionDto(
        id=publication.id,
        title=publication.title,
        funding_source=position.funding_source,
        cost_type=position.item.cost_type.value,
        cost_amount=position.cost.amount,
        tax_rate=Decimal("0.00") if is_vat else position.tax_rate.percentage(),
        external_position_id=position.external_position_id,
        funding_request=funding_request,
        funding_assignments=[
            FundingAssignmentDto(funding_source=f.funding_source, amount=f.amount.amount)
            for f in position.funding_assignments()
        ],
    )


def _is_publicationitem(item: PositionItemType) -> TypeIs[PublicationItem]:
    return isinstance(item, PublicationItem)


class PublicationParser:
    def to_position(
        self, position: PositionDto, currency: Currency, *, parse_safe: bool = False
    ) -> Position:
        assert isinstance(position, PublicationPositionDto)
        return to_position(position, currency, parse_safe=parse_safe)

    def position_to_dto(self, position: Position) -> PositionDto:
        return position_to_dto(position)


parser = PublicationParser()
