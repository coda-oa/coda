from typing import BinaryIO, TextIO

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.dto import CreateFundingRequestDto
from coda.apps.fundingrequests.services.fundingrequests import bulk_create_fundingrequests
from coda.checks.nullcheckfactory import NullCheckFactory

from .dto import FundingRequestImportListDto
from .dtoparsers import fundingrequestdto, publicationdto, reviewdto


def import_fundingrequests(json: TextIO | BinaryIO) -> None:
    import_request_list = FundingRequestImportListDto.model_validate_json(json.read())
    creation_dtos = [
        CreateFundingRequestDto(
            publication=publicationdto.parse_dto(request.publication),
            payment=fundingrequestdto.parse_cost_estimate(request.estimated_cost),
            extra_information=fundingrequestdto.parse_extra_information(request),
            funding=[
                fundingrequestdto.parse_funding(funding) for funding in request.research_funding
            ],
            request_date=request.request_date,
            legacy_request_id=request.legacy_request_id,
        )
        for request in import_request_list.requests
    ]

    ids = bulk_create_fundingrequests(creation_dtos, checkfactory=NullCheckFactory())
    for fundingrequest_id, request in zip(ids, import_request_list.requests):
        review = reviewdto.parse_dto(request.review, fundingrequest_id)
        repository.save_review(review)
