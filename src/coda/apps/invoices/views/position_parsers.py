"""Position parsing functions for invoice position views."""

from collections.abc import Callable
from types import NotImplementedType

from django.http import HttpRequest

from coda import formdata
from coda.apps.fundingrequests import repository
from coda.apps.publications.models import Publication
from coda.contexts.finance.dto.edit_position_dtos import (
    PositionDto,
    PublicationItemDto,
    RelatedFundingRequest,
)
from coda.contexts.finance.services import invoice_parser
from coda.contexts.finance.services.invoice_parser._parser import PositionParseError
from coda.domain.money._currency import Currency
from coda.domain.publication.publication import PublicationId


def added_positions(request: HttpRequest) -> list[PositionDto]:
    """Parse all added positions from request.

    Returns list of PositionDto objects parsed from different position types
    (publication, contract, free-form).
    """
    _positions = [parser(request) for parser in _ADD_POSITION_PARSERS.values()]
    return [p for p in _positions if p is not None]


def parse_added_publication_position(request: HttpRequest) -> PositionDto | None:
    """Parse publication position from request.

    Returns PositionDto if 'add-publication-position' is present in POST data,
    None otherwise.
    """
    publication_id = request.POST.get("add-publication-position")
    if publication_id is None:
        return None

    publication = Publication.objects.get(pk=publication_id)
    return PositionDto(
        item=PublicationItemDto(
            id=publication.pk,
            title=publication.title,
            funding_request=maybe_request_context(publication),
        )
    )


def maybe_request_context(publication: Publication) -> RelatedFundingRequest:
    """Get funding request context for publication if it exists.

    Returns RelatedFundingRequest with request_id and url if publication has
    a funding request reference, empty RelatedFundingRequest otherwise.
    """
    reference = repository.find_reference_by_publication(PublicationId(publication.pk))
    if reference:
        return RelatedFundingRequest(request_id=reference.request_id, url=reference.url)

    return RelatedFundingRequest()


class PositionDtoWithErrors(PositionDto):
    error: str

    @classmethod
    def from_dto(cls, dto: PositionDto, error: str) -> "PositionDtoWithErrors":
        return PositionDtoWithErrors.model_validate(dto.model_dump() | {"error": error})

    def __eq__(self, other: object) -> bool | NotImplementedType:
        """We ignore the error field in comparisons as it is just used as extra information in the view"""
        if not isinstance(other, PositionDto):
            return NotImplemented

        return self.model_dump(exclude={"error"}) == other.model_dump(exclude={"error"})


def _generic_position_parser(prefix: str) -> Callable[[HttpRequest], PositionDto | None]:
    """Create a parser function for positions with given prefix.

    Returns a parser function that extracts POST data with the specified prefix
    and maps it to a PositionDto.
    """

    def parse(request: HttpRequest) -> PositionDto | None:
        filtered_by_prefix = {k: v for k, v in request.POST.items() if k.startswith(prefix)}
        if not filtered_by_prefix:
            return None

        dto = formdata.map_to_model(PositionDto, filtered_by_prefix, prefix=prefix)
        try:
            ignored_currency = Currency.EUR
            invoice_parser.to_position(dto, ignored_currency)
        except PositionParseError as e:
            dto = PositionDtoWithErrors.from_dto(dto, e.message())

        return dto

    return parse


_ADD_POSITION_PARSERS = {
    "publication": parse_added_publication_position,
    "contract": _generic_position_parser("contract"),
    "free": _generic_position_parser("free-position"),
}
