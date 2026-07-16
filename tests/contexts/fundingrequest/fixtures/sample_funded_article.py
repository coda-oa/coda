"""Fixture data for the Crossref article with funders integration test.

This module contains the constants for
"Restoring betatron phase coherence in a beam-loaded laser-wakefield accelerator"
(DOI: 10.1103/physrevaccelbeams.24.091302) — a real Crossref record used to
verify that funders are imported correctly into FundingRequests.
"""

from datetime import date
from typing import Self

from tests import modelfactory

from coda.apps.journals import services as journal_services
from coda.apps.publishers import services as publisher_services
from coda.contexts.fundingrequest.dto.external_metadata import (
    ExternalAuthor,
    ExternalFundingMetadata,
    ExternalFundingOrganisationMetadata,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.contexts.fundingrequest.services.doi_import.doi_client import (
    DOIMetadataClient,
    InMemoryDOIMetadataClient,
)
from coda.domain.author import Author
from coda.domain.fundingrequest import (
    ExternalFunding,
    FundingOrganizationId,
    FundingRequest,
    Payment,
    PaymentMethod,
)
from coda.domain.issn import Issn
from coda.domain.money import Currency, Money
from coda.domain.orcid import Orcid
from coda.domain.publication.links import Doi
from coda.domain.publication.publication import Authors, JournalId, License, Publication, Published
from coda.domain.string import NonEmptyStr

# -- Article identity --

DOI_WITH_FUNDERS = "10.1103/physrevaccelbeams.24.091302"
TITLE = "Restoring betatron phase coherence in a beam-loaded laser-wakefield accelerator"
URL = "https://doi.org/10.1103/physrevaccelbeams.24.091302"

# -- Journal --

JOURNAL_TITLE = "Physical Review Accelerators and Beams"
JOURNAL_EISSN = "2469-9888"
JOURNAL_PUBLISHER = "American Physical Society"

# -- Publication state --

LICENSE = License.CC_BY
PUBLICATION_STATE = Published(online=date(2021, 9, 20))

# -- Authors --

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
        NonEmptyStr("J. P. Couperus Cabadağ"),
        orcid=Orcid("https://orcid.org/0000-0001-9129-4208"),
    ),
    Author.new(
        NonEmptyStr("A. Debus"),
        orcid=Orcid("https://orcid.org/0000-0002-3844-3697"),
    ),
    Author.new(
        NonEmptyStr("J. M. Krämer"),
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

# -- Funders --

FUNDING = [
    {"name": "Helmholtz-Zentrum Dresden-Rossendorf"},
    {
        # NOTE: the publication references the BMFTR by its old name BMBF.
        # This is a good showcase of importing funders by their DOI
        "name": "Bundesministerium für Forschung, Technologie und Raumfahrt",
    },
    {
        "name": "Zentrum für Informationsdienste und Hochleistungsrechnen, Technische Universität Dresden"
    },
    {"name": "EuCARD-2", "project_id": "312453"},
    {"name": "Center of Advanced Systems Understanding"},
    {"name": "Saxon Ministry for Science, Culture and Tourism"},
    {"name": "GWK"},
]

# -- Funder DOIs mapped to canonical names (as resolved by Crossref) --

FUNDER_DOIS: dict[str, str] = {
    "Helmholtz-Zentrum Dresden-Rossendorf": "10.13039/501100008346",
    "Bundesministerium für Forschung, Technologie und Raumfahrt": "10.13039/501100002347",
    "Zentrum für Informationsdienste und Hochleistungsrechnen, Technische Universität Dresden": "",  # no DOI
    "EuCARD-2": "10.13039/501100019676",
    "Center of Advanced Systems Understanding": "",  # no DOI
    "Saxon Ministry for Science, Culture and Tourism": "",  # no DOI
    "GWK": "",  # no DOI
}


class FundedArticleScenario:
    """Scenario for importing a Crossref article with funders via DOI."""

    def __init__(self, doi_client: DOIMetadataClient) -> None:
        self._doi_client = doi_client
        self._journal_id: int | None = None
        self._funding_org_ids: dict[str, FundingOrganizationId] = {}

    @property
    def doi(self) -> Doi:
        return Doi(DOI_WITH_FUNDERS)

    @property
    def client(self) -> DOIMetadataClient:
        return self._doi_client

    @property
    def journal_id(self) -> int:
        if self._journal_id is None:
            raise RuntimeError("setup_db() must be called before accessing journal_id")
        return self._journal_id

    @staticmethod
    def with_in_memory_client() -> "FundedArticleScenario":
        client = InMemoryDOIMetadataClient()
        scenario = FundedArticleScenario(client)
        scenario._configure_client(client)
        return scenario

    def setup_db(self) -> Self:
        publisher_id = publisher_services.create(JOURNAL_PUBLISHER)
        self._journal_id = int(
            journal_services.create(
                title=NonEmptyStr(JOURNAL_TITLE),
                eissn=Issn(JOURNAL_EISSN),
                publisher_id=publisher_id,
            )
        )
        for funder_info in FUNDING:
            org = modelfactory.funding_organization(funder_info["name"])
            self._funding_org_ids[funder_info["name"]] = FundingOrganizationId(org.pk)
        if isinstance(self._doi_client, InMemoryDOIMetadataClient):
            self._configure_client(self._doi_client)

        return self

    def _configure_client(self, client: InMemoryDOIMetadataClient) -> None:
        external_authors = [
            ExternalAuthor(
                name=a.name,
                orcid=str(a.orcid) if a.orcid else None,
                affiliation=None,
            )
            for a in AUTHORS
        ]

        funders = []
        for funder_info in FUNDING:
            funder_doi = FUNDER_DOIS.get(funder_info["name"], "")
            identifiers = [funder_doi] if funder_doi else []
            if funder_doi and "/" in funder_doi:
                suffix = funder_doi.rsplit("/", 1)[-1]
                identifiers.append(suffix)
            funders.append(
                ExternalFundingMetadata(
                    funder=ExternalFundingOrganisationMetadata(
                        name=funder_info["name"],
                        identifiers=identifiers,
                    ),
                    project_id=funder_info.get("project_id", ""),
                )
            )

        client.data[DOI_WITH_FUNDERS] = ExternalPublicationMetadata(
            title=TITLE,
            authors=external_authors,
            publication_type="journal-article",
            journal=ExternalJournal(
                title=JOURNAL_TITLE,
                eissn=JOURNAL_EISSN,
            ),
            publisher=JOURNAL_PUBLISHER,
            license="CC-BY",
            online_publication_date=date(2021, 9, 20),
            funders=funders,
        )

        # NOTE: funder resolution via ROR no longer needs configure_funder.
        # Funder names from Crossref metadata are used directly when ROR
        # does not have a match.

    def get_expected_fundingrequest(self) -> FundingRequest[Publication]:
        expected_publication = Publication.new(
            title=NonEmptyStr(TITLE),
            journal=JournalId(self.journal_id),
            relevant_authors=Authors(AUTHORS),
            links={self.doi},
            license=LICENSE,
            publication_state=PUBLICATION_STATE,
        )

        return FundingRequest.new(
            publication=expected_publication,
            estimated_cost=Payment(Money(0, Currency.EUR), PaymentMethod.Unknown),
            external_funding=[
                ExternalFunding(
                    self._funding_org_ids[funder["name"]],
                    project_id=funder.get("project_id", ""),
                    project_name="",
                )
                for funder in FUNDING
            ],
        )
