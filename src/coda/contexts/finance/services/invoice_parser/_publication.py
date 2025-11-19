from typing_extensions import TypeIs

from coda.apps.fundingrequests import repository
from coda.apps.publications.repositories import publication_repository
from coda.contexts.finance.dto.edit_position_dtos import (
    ItemDto,
    PositionDto,
    PublicationItemDto,
    RelatedFundingRequest,
)
from coda.domain.finance.costtypes import PublicationCostType
from coda.domain.finance.invoice_positions import Position, PositionItemType, PublicationItem
from coda.domain.publication.publication import PublicationId


def _parse_item(position: PositionDto, *, parse_safe: bool = True) -> PublicationId:
    assert isinstance(position.item, PublicationItemDto)
    _ = parse_safe
    return PublicationId(position.item.id)


def _parse_cost_type(position: PositionDto) -> PublicationCostType:
    return PublicationCostType(position.cost_type)


def parse_item_from(position: PositionDto, *, parse_safe: bool = False) -> PositionItemType:
    return PublicationItem(_parse_item(position, parse_safe=parse_safe), _parse_cost_type(position))


def to_itemdto(position: Position) -> ItemDto:
    assert _is_publicationitem(position.item)
    publication = publication_repository.get_by_id(position.item.item)
    assert publication.id is not None

    funding_request = RelatedFundingRequest()
    reference = repository.find_reference_by_publication(publication.id)
    if reference:
        funding_request = RelatedFundingRequest(
            request_id=reference.request_id,
            url=reference.url,
        )

    return PublicationItemDto(
        id=publication.id,
        title=publication.title,
        cost_type=position.item.cost_type.value,
        funding_request=funding_request,
    )


def _is_publicationitem(item: PositionItemType) -> TypeIs[PublicationItem]:
    return isinstance(item, PublicationItem)


class PublicationParser:
    def to_itemdto(self, position: Position) -> ItemDto:
        return to_itemdto(position)

    def parse_item_from(
        self, position: PositionDto, *, parse_safe: bool = False
    ) -> PositionItemType:
        return parse_item_from(position, parse_safe=parse_safe)


parser = PublicationParser()
