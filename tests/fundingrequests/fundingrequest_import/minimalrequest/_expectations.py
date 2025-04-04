import datetime

from coda.apps.journals import services as journal_services
from coda.apps.publishers.models import Publisher
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import (
    FundingRequest,
    FundingRequestId,
    Payment,
    PaymentMethod,
    PublicFundingRequestId,
    Review,
)
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.publication import JournalId, License, OpenAccessType, Publication
from coda.domain.publication.publication import Monograph
from coda.domain.string import NonEmptyStr
from tests.fundingrequests.fundingrequest_import.entitynames import (
    IMPORT_JOURNAL_ISSN,
    IMPORT_PUBLICATION_TITLE,
    IMPORT_PUBLISHER_NAME,
)


def expected_article_request() -> FundingRequest[Publication]:
    journal = journal_services.find_by_eissn(IMPORT_JOURNAL_ISSN)
    assert journal is not None

    journal_id = JournalId(journal.id)

    request_date = datetime.date(2025, 3, 19)
    request_id = PublicFundingRequestId.create(date=request_date)
    return FundingRequest.new(
        publication=Publication.new(
            title=IMPORT_PUBLICATION_TITLE,
            journal=journal_id,
            license=License.CC_BY,
            open_access_type=OpenAccessType.Gold,
        ),
        estimated_cost=Payment(
            amount=Money("0.00", currency=Currency.EUR),
            method=PaymentMethod.Unknown,
        ),
        request_id=request_id,
    )


def expected_review(id: FundingRequestId | None = None) -> Review:
    return Review(
        fundingrequest=id,
        result=ReviewResult.Open,
        decided_funding=Money("0.00", Currency.EUR),
    )


def expected_monograph_request() -> FundingRequest[Monograph]:
    publisher = Publisher.objects.get(name=IMPORT_PUBLISHER_NAME)
    monograph = Monograph.new(
        title=NonEmptyStr("My article"),
        publisher=PublisherId(publisher.id),
        license=License.CC_BY,
        open_access_type=OpenAccessType.Gold,
    )

    request_date = datetime.date(2025, 3, 19)
    request_id = PublicFundingRequestId.create(date=request_date)
    return FundingRequest(
        id=None,
        publication=monograph,
        estimated_cost=Payment(
            amount=Money("0.00", currency=Currency.EUR),
            method=PaymentMethod.Unknown,
        ),
        request_id=request_id,
        review=expected_review(),
    )
