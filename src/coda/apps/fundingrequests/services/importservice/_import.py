from typing import BinaryIO, TextIO

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.services.fundingrequests import create_fundingrequest
from coda.checks.nullcheckfactory import NullCheckFactory

from .dto import FundingRequestImportListDto
from .dtoparsers import fundingrequestdto, publicationdto, reviewdto


def import_fundingrequests(json: TextIO | BinaryIO) -> None:
    import_request_list = FundingRequestImportListDto.model_validate_json(json.read())
    for request in import_request_list.requests:
        fundingrequest_id = create_fundingrequest(
            publication=publicationdto.parse_dto(request.publication),
            payment=fundingrequestdto.parse_cost_estimate(request.estimated_cost),
            extra_information=fundingrequestdto.parse_extra_information(request),
            funding=[
                fundingrequestdto.parse_funding(funding) for funding in request.research_funding
            ],
            request_date=request.request_date,
            checkfactory=NullCheckFactory(),
        )

        review = reviewdto.parse_dto(request.review, fundingrequest_id)
        repository.save_review(review)
