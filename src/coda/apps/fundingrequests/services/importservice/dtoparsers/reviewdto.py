from coda.domain.fundingrequest import FundingRequestId, Review
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money

from ..dto import ReviewImportDto


def parse_dto(import_dto: ReviewImportDto, fundingrequest: FundingRequestId) -> Review:
    return Review(
        fundingrequest=fundingrequest,
        result=import_dto.result,
        remarks=import_dto.remarks,
        decided_funding=_parse_funding(import_dto),
    )


def _parse_funding(import_dto: ReviewImportDto) -> Money:
    return Money(
        amount=import_dto.funding.amount,
        currency=Currency.from_code(import_dto.funding.currency),
    )
