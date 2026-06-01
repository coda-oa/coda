from datetime import date

import pytest
from coda.apps.fundingrequests import repository
from coda.contexts.publication.services.doi_client import CrossrefDoiClient
from coda.contexts.publication.services.doi_import_service import DOIImportService
from coda.domain.publication.links import Doi
from tests import modelfactory

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.domain.author import Author
from coda.domain.fundingrequest import FundingRequest
from coda.domain.fundingrequest.fundingrequest import (
    ExternalFunding,
    FundingOrganizationId,
    Payment,
    PaymentMethod,
)
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.orcid import Orcid
from coda.domain.publication.publication import Authors, JournalId, License, Publication, Published
from coda.domain.string import NonEmptyStr
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq

TITLE = "Restoring betatron phase coherence in a beam-loaded laser-wakefield accelerator"
DOI_WITH_FUNDERS = "10.1103/physrevaccelbeams.24.091302"
URL = "https://doi.org/10.1103/physrevaccelbeams.24.091302"
LICENSE = License.CC_BY
JOURNAL_TITLE = "Physical Review Accelerators and Beams"
JOURNAL_EISSN = "2469-9888"
JOURNAL_PUBLISHER = "American Physical Society"
PUBLICATION_STATE = Published(online=date(2021, 9, 20))


AUTHORS = [
    Author.new(
        NonEmptyStr("A. Koehler"),
        orcid=Orcid("https://orcid.org/0000-0001-9759-1166"),
    ),
    Author.new(
        NonEmptyStr("R. Pausch"),
        orcid=Orcid("https://orcid.org/0000-0001-7990-9564"),
    ),
    Author.new(
        NonEmptyStr("M. Bussmann"),
        orcid=Orcid("https://orcid.org/0000-0002-8258-3881"),
    ),
    Author.new(
        NonEmptyStr("J. P. Couperus Cabadağ"),
        orcid=Orcid("https://orcid.org/0000-0001-9129-4208"),
    ),
    Author.new(
        NonEmptyStr("A. Debus"),
        orcid=Orcid("https://orcid.org/0000-0002-3844-3697"),
    ),
    Author.new(
        NonEmptyStr("J. M. Krämer"),
        orcid=Orcid("https://orcid.org/0000-0003-2720-2465"),
    ),
    Author.new(
        NonEmptyStr("S. Schöbel"),
        orcid=Orcid("https://orcid.org/0000-0002-2769-4749"),
    ),
    Author.new(NonEmptyStr("O. Zarini")),
    Author.new(
        NonEmptyStr("U. Schramm"),
        orcid=Orcid("https://orcid.org/0000-0003-0390-7671"),
    ),
    Author.new(
        NonEmptyStr("A. Irman"),
        orcid=Orcid("https://orcid.org/0000-0002-4626-0049"),
    ),
]


FUNDING = [
    {"name": "Helmholtz-Zentrum Dresden-Rossendorf"},
    {
        # NOTE: the pulication references the BMFTR by its old name BMBF.
        # This is a good showcase of importing funders by their DOI
        "name": "Bundesministerium für Forschung, Technologie und Raumfahrt"
    },
    {
        "name": "Zentrum für Informationsdienste und Hochleistungsrechnen, Technische Universität Dresden"
    },
    {"name": "EuCARD-2", "project_id": "312453"},
    {"name": "Center of Advanced Systems Understanding"},
    {"name": "Saxon Ministry for Science, Culture and Tourism"},
    {"name": "GWK"},
]


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
    doi_client = CrossrefDoiClient()
    sut = DOIImportService(doi_client)

    fr_id = sut.import_from_doi(Doi(DOI_WITH_FUNDERS))

    actual = repository.get_by_id(fr_id)
    assert_fundingrequest_eq(actual, expected)
