import datetime

from coda.apps.journals import services as journal_services
from coda.apps.publishers.models import Publisher
from coda.contract import PublisherId
from coda.fundingrequest import FundingRequest, Payment, PaymentMethod, PublicFundingRequestId
from coda.money import Currency, Money
from coda.publication import JournalId, License, OpenAccessType, Publication
from coda.publication.publication import Monograph
from coda.string import NonEmptyStr
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
    return FundingRequest.new(
        publication=monograph,
        estimated_cost=Payment(
            amount=Money("0.00", currency=Currency.EUR),
            method=PaymentMethod.Unknown,
        ),
        request_id=request_id,
    )
