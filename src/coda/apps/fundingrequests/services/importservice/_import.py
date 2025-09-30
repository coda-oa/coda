from dataclasses import dataclass
from typing import BinaryIO, TextIO

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import CreateFundingRequestDto
from coda.apps.fundingrequests.services.fundingrequests import bulk_create_fundingrequests
from coda.apps.fundingrequests.services.importservice.dto._fundingrequest import (
    FundingRequestImportDto,
)
from coda.checks.nullcheckfactory import NullCheckFactory

from .dto import FundingRequestImportListDto
from .dtoparsers import fundingrequestdto, publicationdto, reviewdto


@dataclass(frozen=True)
class FundingRequestImportReport:
    valid_requests: int
    invalid_requests: int
    errors: dict[str, list[str]]


def try_into_dto(
    request: FundingRequestImportDto, errors: dict[str, list[str]]
) -> CreateFundingRequestDto | None:
    try:
        return CreateFundingRequestDto(
            publication=publicationdto.parse_dto(request.publication),
            payment=fundingrequestdto.parse_cost_estimate(request.estimated_cost),
            extra_information=fundingrequestdto.parse_extra_information(request),
            funding=[
                fundingrequestdto.parse_funding(funding) for funding in request.research_funding
            ],
            request_date=request.request_date,
            legacy_request_id=request.legacy_request_id,
        )
    except ValueError as e:
        error_key = request.legacy_request_id or request.publication.title
        errors.setdefault(error_key, []).append(str(e))
        return None


def import_fundingrequests(json: TextIO | BinaryIO) -> FundingRequestImportReport:
    errors: dict[str, list[str]] = {}
    import_request_list = FundingRequestImportListDto.model_validate_json(json.read())
    _creation_dtos = [try_into_dto(request, errors) for request in import_request_list.requests]
    creation_dtos = [dto for dto in _creation_dtos if dto is not None]

    ids, create_errors = bulk_create_fundingrequests(creation_dtos, checkfactory=NullCheckFactory())
    for e in create_errors:
        errors.setdefault(e.request_key, []).append(e.reason)

    for fundingrequest_id, request in zip(ids, import_request_list.requests):
        review = reviewdto.parse_dto(request.review, fundingrequest_id)
        repository.save_review(review)

    return FundingRequestImportReport(len(tuple(ids)), len(errors), errors)
