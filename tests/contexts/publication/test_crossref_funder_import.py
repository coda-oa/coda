"""Tests for DOI import with funders (using fake clients).

Verifies that funders referenced in Crossref metadata are correctly
resolved and imported into FundingRequests — without hitting live APIs.
"""

import pytest
from tests import modelfactory
from tests.contexts.publication.fixtures.sample_funded_article import (
    AUTHORS,
    DOI_WITH_FUNDERS,
    FUNDING,
    JOURNAL_EISSN,
    JOURNAL_PUBLISHER,
    JOURNAL_TITLE,
    LICENSE,
    PUBLICATION_STATE,
    TITLE,
    configure_funded_article_client,
)
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq

from coda.apps.fundingrequests import repository
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.contexts.publication.services.doi_client import InMemoryDOIMetadataClient
from coda.contexts.publication.services.doi_import_service import DOIImportService
from coda.domain.fundingrequest import FundingRequest
from coda.domain.fundingrequest.fundingrequest import (
    ExternalFunding,
    FundingOrganizationId,
    Payment,
    PaymentMethod,
)
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.publication.links import Doi
from coda.domain.publication.publication import Authors, JournalId, Publication
from coda.domain.string import NonEmptyStr


def expected_fundingrequest() -> FundingRequest[Publication]:
    fr = FundingRequest.new(
        Publication.new(
            title=NonEmptyStr(TITLE),
            journal=JournalId(
                Journal.objects.create(
                    title=JOURNAL_TITLE,
                    eissn=JOURNAL_EISSN,
                    publisher=Publisher.objects.create(name=JOURNAL_PUBLISHER),
                ).pk
            ),
            relevant_authors=Authors(AUTHORS),
            links={Doi(DOI_WITH_FUNDERS)},
            license=LICENSE,
            publication_state=PUBLICATION_STATE,
        ),
        estimated_cost=Payment(Money(0, Currency.EUR), PaymentMethod.Unknown),
        external_funding=[
            ExternalFunding(
                FundingOrganizationId(modelfactory.funding_organization(funder["name"]).pk),
                project_id=funder.get("project_id", ""),
                project_name="",
            )
            for funder in FUNDING
        ],
    )
    return fr


@pytest.mark.django_db
def test__doi_with_funders__imports_funders_into_fundingrequest() -> None:
    expected = expected_fundingrequest()
    fake_client = InMemoryDOIMetadataClient()
    configure_funded_article_client(fake_client)
    sut = DOIImportService(fake_client)

    fr_id = sut.import_from_doi(Doi(DOI_WITH_FUNDERS))

    actual = repository.get_by_id(fr_id)
    assert_fundingrequest_eq(actual, expected)
