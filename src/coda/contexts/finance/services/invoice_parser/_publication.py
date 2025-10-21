from decimal import Decimal

from coda.apps.fundingrequests import repository
from coda.apps.publications.repositories import publication_repository
from coda.contexts.finance.dto.edit_position_dtos import (
    AnyPositionDto,
    PublicationPositionDto,
    RelatedFundingRequest,
)
from coda.domain.invoice import (
    AnyPosition,
    FundingSourceId,
    Position,
    PublicationCostType,
    TaxRate,
)
from coda.domain.money import Currency, Money
from coda.domain.publication.publication import PublicationId


def parse_item(position: PublicationPositionDto, *, parse_safe: bool = True) -> PublicationId:
    _ = parse_safe
    return PublicationId(position.id)


def parse_cost_type(position: PublicationPositionDto) -> PublicationCostType:
    return PublicationCostType(position.cost_type)


def to_position(
    position: PublicationPositionDto, currency: Currency, *, parse_safe: bool = False
) -> Position[PublicationId]:
    return Position(
        item=parse_item(position, parse_safe=parse_safe),
        cost=Money(position.cost_amount, currency),
        tax_rate=TaxRate.from_percentage(position.tax_rate),
        cost_type=parse_cost_type(position),
        external_position_id=position.external_position_id,
        funding_source=FundingSourceId(position.funding_source)
        if position.funding_source
        else None,
    )


def position_to_dto(position: Position[PublicationId]) -> PublicationPositionDto:
    publication = publication_repository.get_by_id(position.item)
    assert publication.id is not None

    is_vat = position.cost_type == PublicationCostType.Vat

    funding_request = RelatedFundingRequest()
    reference = repository.find_reference_by_publication(publication.id)
    if reference:
        funding_request = RelatedFundingRequest(request_id=reference.request_id, url=reference.url)

    return PublicationPositionDto(
        id=publication.id,
        title=publication.title,
        funding_source=position.funding_source,
        cost_type=position.cost_type.value,
        cost_amount=position.cost.amount,
        tax_rate=Decimal("0.00") if is_vat else position.tax_rate.percentage(),
        external_position_id=position.external_position_id,
        funding_request=funding_request,
    )


class PublicationParser:
    def to_position(
        self, position: AnyPositionDto, currency: Currency, *, parse_safe: bool = False
    ) -> AnyPosition:
        assert isinstance(position, PublicationPositionDto)
        return to_position(position, currency, parse_safe=parse_safe)

    def position_to_dto(self, position: AnyPosition) -> AnyPositionDto:
        assert isinstance(position, Position) and isinstance(position.item, PublicationId)
        return position_to_dto(position)


parser = PublicationParser()
