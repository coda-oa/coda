from typing import TypeIs

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
    return PublicationCostType(position.item.cost_type)


def parse_item_from(position: PositionDto, *, parse_safe: bool = False) -> PositionItemType:
    return PublicationItem(_parse_item(position, parse_safe=parse_safe), _parse_cost_type(position))


def to_itemdto(position: Position) -> ItemDto:
    assert _is_publicationitem(position.item)

    publication_reference = publication_repository.get_publication_reference(position.item.item)
    if not publication_reference:
        raise ValueError("Request not found")

    funding_request = RelatedFundingRequest()
    if request_ref := publication_reference.fundingrequest_reference:
        funding_request = RelatedFundingRequest(
            request_id=request_ref.request_id,
            url=request_ref.url,
        )

    return PublicationItemDto(
        id=publication_reference.id,
        title=publication_reference.title,
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
