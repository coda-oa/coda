"""Test metadata fixtures for DOI import tests.

This module contains scenario classes that encapsulate DOI metadata,
client configuration, and expected FundingRequest outcomes for
common test cases.
"""

import datetime

from coda.apps.journals import services as journal_services
from coda.apps.publishers import services as publisher_services
from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.contexts.publication.services.doi_client import (
    DOIMetadataClient,
    InMemoryDOIMetadataClient,
)
from coda.domain.author import Author, Role
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest, Payment, PaymentMethod
from coda.domain.issn import Issn
from coda.domain.money import Currency, Money
from coda.domain.publication import (
    Authors,
    JournalId,
    License,
    Monograph,
    Publication,
    Published,
)
from coda.domain.publication.links import Doi, Isbn
from coda.domain.string import NonEmptyStr

NATURE_ARTICLE_DOI = "10.1038/nature12373"
NATURE_JOURNAL_TITLE = "Nature"
NATURE_EISSN = "1476-4687"
SPRINGER_NATURE_PUBLISHER = "Springer Nature"

SPRINGER_BOOK_DOI = "10.1007/978-3-319-18938-3"
SPRINGER_BOOK_ISBN = "9783319189376"
SPRINGER_BOOK_TITLE = "Quantum Microscopy of Biological Systems"
SPRINGER_BOOK_PUBLISHER = "Springer International Publishing"


class NatureArticleScenario:
    """Scenario for importing a Nature journal article via DOI."""

    def __init__(self, doi_client: DOIMetadataClient, doi: str | None = None) -> None:
        self._doi_client = doi_client
        self._doi = doi or NATURE_ARTICLE_DOI
        self._journal_id: int | None = None

    @property
    def doi(self) -> Doi:
        return Doi(self._doi)

    @property
    def client(self) -> DOIMetadataClient:
        return self._doi_client

    @property
    def journal_id(self) -> int:
        if self._journal_id is None:
            raise RuntimeError("setup_db() must be called before accessing journal_id")
        return self._journal_id

    @staticmethod
    def with_in_memory_client(doi: str | None = None) -> "NatureArticleScenario":
        client = InMemoryDOIMetadataClient()
        scenario = NatureArticleScenario(client, doi)
        scenario._configure_client(client)
        return scenario

    def setup_db(self) -> None:
        publisher_id = publisher_services.create(SPRINGER_NATURE_PUBLISHER)
        self._journal_id = int(
            journal_services.create(
                title=NonEmptyStr(NATURE_JOURNAL_TITLE),
                eissn=Issn(NATURE_EISSN),
                publisher_id=publisher_id,
            )
        )
        if isinstance(self._doi_client, InMemoryDOIMetadataClient):
            self._configure_client(self._doi_client)

    def _configure_client(self, client: InMemoryDOIMetadataClient) -> None:
        client.data[str(self._doi)] = ExternalPublicationMetadata(
            title="Nanometre-scale thermometry in a living cell",
            authors=[
                ExternalAuthor(
                    name="G. Kucsko",
                    affiliation=None,
                    ror_id=None,
                ),
                ExternalAuthor(
                    name="P. C. Maurer",
                    affiliation=None,
                    ror_id=None,
                ),
                ExternalAuthor(
                    name="N. Y. Yao",
                    affiliation=None,
                    ror_id=None,
                ),
                ExternalAuthor(
                    name="M. Kubo",
                    affiliation=None,
                    ror_id=None,
                ),
                ExternalAuthor(
                    name="H. J. Noh",
                    affiliation=None,
                    ror_id=None,
                ),
                ExternalAuthor(
                    name="P. K. Lo",
                    affiliation=None,
                    ror_id=None,
                ),
                ExternalAuthor(
                    name="H. Park",
                    affiliation=None,
                    ror_id=None,
                ),
                ExternalAuthor(
                    name="M. D. Lukin",
                    affiliation=None,
                    ror_id=None,
                ),
            ],
            publication_type="journal-article",
            journal=ExternalJournal(
                title=NATURE_JOURNAL_TITLE,
                issn="0028-0836",
                eissn=NATURE_EISSN,
            ),
            publisher="Springer Science and Business Media LLC",
            license="https://creativecommons.org/licenses/by/4.0/",
            online_publication_date=datetime.date(2013, 7, 31),
            print_publication_date=datetime.date(2013, 8, 1),
        )

    def get_expected_fundingrequest(self) -> FundingRequest[Publication]:
        expected_authors = Authors(
            [
                Author.new(name=NonEmptyStr("G. Kucsko"), role=Role.CO_AUTHOR),
                Author.new(name=NonEmptyStr("P. C. Maurer"), role=Role.CO_AUTHOR),
                Author.new(name=NonEmptyStr("N. Y. Yao"), role=Role.CO_AUTHOR),
                Author.new(name=NonEmptyStr("M. Kubo"), role=Role.CO_AUTHOR),
                Author.new(name=NonEmptyStr("H. J. Noh"), role=Role.CO_AUTHOR),
                Author.new(name=NonEmptyStr("P. K. Lo"), role=Role.CO_AUTHOR),
                Author.new(name=NonEmptyStr("H. Park"), role=Role.CO_AUTHOR),
                Author.new(name=NonEmptyStr("M. D. Lukin"), role=Role.CO_AUTHOR),
            ]
        )

        expected_publication = Publication.new(
            title=NonEmptyStr("Nanometre-scale thermometry in a living cell"),
            journal=JournalId(self.journal_id),
            relevant_authors=expected_authors,
            license=License.Unknown,
            publication_state=Published(
                online=datetime.date(2013, 7, 31),
                print=datetime.date(2013, 8, 1),
            ),
            links={self.doi},
        )

        return FundingRequest.new(
            publication=expected_publication,
            estimated_cost=Payment(
                amount=Money(0, Currency.EUR),
                method=PaymentMethod.Unknown,
            ),
        )


class SpringerBookScenario:
    """Scenario for importing a Springer book (monograph) via DOI."""

    def __init__(self, doi_client: DOIMetadataClient, doi: str | None = None) -> None:
        self._doi_client = doi_client
        self._doi = doi or SPRINGER_BOOK_DOI
        self._publisher_id: int | None = None

    @property
    def doi(self) -> Doi:
        return Doi(self._doi)

    @property
    def client(self) -> DOIMetadataClient:
        return self._doi_client

    @property
    def publisher_id(self) -> int:
        if self._publisher_id is None:
            raise RuntimeError("setup_db() must be called before accessing publisher_id")
        return self._publisher_id

    @staticmethod
    def with_in_memory_client(doi: str | None = None) -> "SpringerBookScenario":
        client = InMemoryDOIMetadataClient()
        scenario = SpringerBookScenario(client, doi)
        scenario._configure_client(client)
        return scenario

    def setup_db(self) -> None:
        self._publisher_id = int(publisher_services.create(SPRINGER_BOOK_PUBLISHER))
        if isinstance(self._doi_client, InMemoryDOIMetadataClient):
            self._configure_client(self._doi_client)

    def _configure_client(self, client: InMemoryDOIMetadataClient) -> None:
        client.data[str(self._doi)] = ExternalPublicationMetadata(
            title=SPRINGER_BOOK_TITLE,
            authors=[
                ExternalAuthor(
                    name="Michael Taylor",
                    affiliation=None,
                    ror_id=None,
                ),
            ],
            publication_type="book",
            journal=None,
            isbn=SPRINGER_BOOK_ISBN,
            publisher=SPRINGER_BOOK_PUBLISHER,
            license=None,
            print_publication_date=datetime.date(2015, 1, 1),
        )

    def get_expected_fundingrequest(self) -> FundingRequest[Monograph]:
        expected_authors = Authors(
            [
                Author.new(name=NonEmptyStr("Michael Taylor"), role=Role.CO_AUTHOR),
            ]
        )

        expected_monograph = Monograph.new(
            title=NonEmptyStr(SPRINGER_BOOK_TITLE),
            publisher=PublisherId(self.publisher_id),
            relevant_authors=expected_authors,
            license=License.Unknown,
            publication_state=Published(print=datetime.date(2015, 1, 1)),
            links={self.doi, Isbn(SPRINGER_BOOK_ISBN)},
        )

        return FundingRequest.new(
            publication=expected_monograph,
            estimated_cost=Payment(
                amount=Money(0, Currency.EUR),
                method=PaymentMethod.Unknown,
            ),
        )
