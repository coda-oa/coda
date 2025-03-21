from typing import TextIO

from coda.apps.fundingrequests import repository

from .dto import FundingRequestImportListDto


def import_fundingrequests(json: TextIO) -> None:
    import_request_list = FundingRequestImportListDto.model_validate_json(json.read())
    for request in import_request_list.requests:
        fundingrequest = request.parse()
        fundingrequest.id = repository.save(fundingrequest)
        review = request.review.parse(fundingrequest.id)
        repository.save_review(review)
