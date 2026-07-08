"""Test metadata fixtures for DOI import tests.

This module contains scenario classes that encapsulate DOI metadata,
client configuration, and expected FundingRequest outcomes for
common test cases.
"""

import datetime
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Self

from tests import modelfactory
from tests.contexts.publication.fixtures.metadata import article_metadata, book_metadata

from coda.apps.journals import services as journal_services
from coda.apps.publishers import services as publisher_services
from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalFundingMetadata,
    ExternalFundingOrganisationMetadata,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.contexts.publication.services.doi_client import (
    DOIMetadataClient,
    InMemoryDOIMetadataClient,
)
from coda.domain import orcid
from coda.domain.author import Author, AuthorNames, Role
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import (
    FundingRequest,
    NoContact,
    Payment,
    PaymentMethod,
)
from coda.domain.fundingrequest.fundingrequest import ExternalFunding, FundingOrganizationId
from coda.domain.issn import Issn
from coda.domain.money import Currency, Money
from coda.domain.publication import (
    Authors,
    JournalId,
    License,
    Monograph,
    OpenAccessType,
    Publication,
    Published,
)
from coda.domain.publication.links import Doi, Isbn
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import UnknownConcept

NATURE_ARTICLE_DOI = "10.1038/nature12373"
NATURE_JOURNAL_TITLE = "Nature"
NATURE_EISSN = "1476-4687"
SPRINGER_NATURE_PUBLISHER = "Springer Science and Business Media LLC"

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

    def setup_db(self) -> "NatureArticleScenario":
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

        return self

    def _configure_client(self, client: InMemoryDOIMetadataClient) -> None:
        client.data[self._doi] = ExternalPublicationMetadata(
            title="Nanometre-scale thermometry in a living cell",
            authors=[
                ExternalAuthor(
                    name="G. Kucsko",
                    affiliation=None,
                    orcid=None,
                ),
                ExternalAuthor(
                    name="P. C. Maurer",
                    affiliation=None,
                    orcid=None,
                ),
                ExternalAuthor(
                    name="N. Y. Yao",
                    affiliation=None,
                    orcid=None,
                ),
                ExternalAuthor(
                    name="M. Kubo",
                    affiliation=None,
                    orcid=None,
                ),
                ExternalAuthor(
                    name="H. J. Noh",
                    affiliation=None,
                    orcid=None,
                ),
                ExternalAuthor(
                    name="P. K. Lo",
                    affiliation=None,
                    orcid=None,
                ),
                ExternalAuthor(
                    name="H. Park",
                    affiliation=None,
                    orcid=None,
                ),
                ExternalAuthor(
                    name="M. D. Lukin",
                    affiliation=None,
                    orcid=None,
                ),
            ],
            publication_type="journal-article",
            journal=ExternalJournal(
                title=NATURE_JOURNAL_TITLE,
                issn="0028-0836",
                eissn=NATURE_EISSN,
            ),
            publisher=SPRINGER_NATURE_PUBLISHER,
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
        client.data[self._doi] = ExternalPublicationMetadata(
            title=SPRINGER_BOOK_TITLE,
            authors=[
                ExternalAuthor(
                    name="Michael Taylor",
                    affiliation=None,
                    orcid=None,
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


PREVIEW_ARTICLE_DOI = "10.1234/preview.test"
PREVIEW_ARTICLE_TITLE = "Test DOI Preview Article"
PREVIEW_JOURNAL_TITLE = "Test Journal"
PREVIEW_JOURNAL_EISSN = "1234-1231"
PREVIEW_PUBLISHER_NAME = "Test Publisher"

type Name = str
type Affiliation = str | None
type Orcid = str | None

type FunderName = str
type ProjectId = str


class _BaseScenario(ABC):
    def __init__(self, doi: str, client: InMemoryDOIMetadataClient | None = None) -> None:
        self._client = client or InMemoryDOIMetadataClient()
        self._doi_str = doi
        self._title = ""
        self._publisher_name: str | None = None
        self._online_publication_date: datetime.date | None = datetime.date.min
        self._print_publication_date: datetime.date | None = datetime.date.min
        self._authors: list[tuple[Name, Affiliation, Orcid]] = []
        self._has_error = False
        self._license: str | None = None
        self._funding: list[tuple[FunderName, ProjectId | None, Doi | None]] = []
        self._funder_lookup: dict[FunderName, FundingOrganizationId] = {}

    @property
    def doi(self) -> Doi:
        return Doi(self._doi_str)

    @property
    def client(self) -> DOIMetadataClient:
        return self._client

    @property
    def metadata(self) -> ExternalPublicationMetadata:
        return self._build_metadata()

    def setup_client(self) -> Self:
        if self._has_error:
            self._client.configure_error(Doi(self._doi_str), "network")
        else:
            self._client.data[self._doi_str] = self._build_metadata()
        return self

    @abstractmethod
    def _build_metadata(self) -> ExternalPublicationMetadata: ...

    def with_title(self, title: str) -> Self:
        self._title = title
        return self

    def with_authors(self, *authors: tuple[Name, Affiliation, Orcid]) -> Self:
        self._authors = list(authors)
        return self

    def with_publisher(self, name: str) -> Self:
        self._publisher_name = name
        return self

    def without_publisher(self) -> Self:
        self._publisher_name = None
        return self

    def with_online_date(self, date: datetime.date) -> Self:
        self._online_publication_date = date
        return self

    def with_print_date(self, date: datetime.date) -> Self:
        self._print_publication_date = date
        return self

    def without_online_date(self) -> Self:
        self._online_publication_date = None
        return self

    def without_print_date(self) -> Self:
        self._print_publication_date = None
        return self

    def with_invalid_license(self) -> Self:
        self._license = "INVALID-LICENSE"
        return self

    def with_funding(
        self, funding: Iterable[tuple[FunderName, ProjectId | None, Doi | None]]
    ) -> Self:
        self._funding = list(funding)
        return self

    def with_funder_doi(self, funder_name: str, doi: str) -> Self:
        doi_obj = Doi(doi)
        for i, (name, project_id, _) in enumerate(self._funding):
            if name == funder_name:
                self._funding[i] = (name, project_id, doi_obj)
                return self
        msg = f"Funder '{funder_name}' not found in funding list"
        raise ValueError(msg)

    def with_error(self) -> Self:
        self._has_error = True
        return self


class ArticleScenario(_BaseScenario):
    """Scenario for importing a journal article via DOI. Auto-derives expected FundingRequest."""

    def __init__(
        self, client: InMemoryDOIMetadataClient | None = None, doi: str = PREVIEW_ARTICLE_DOI
    ) -> None:
        super().__init__(doi, client)
        self._journal_id: int | None = None
        self._title = PREVIEW_ARTICLE_TITLE
        self._publisher_name: str | None = PREVIEW_PUBLISHER_NAME
        self._journal_title = PREVIEW_JOURNAL_TITLE
        self._eissn: str | None = PREVIEW_JOURNAL_EISSN
        self._issn: str | None = None

    def with_journal(
        self,
        title: str = PREVIEW_JOURNAL_TITLE,
        eissn: str | None = PREVIEW_JOURNAL_EISSN,
        publisher: str = PREVIEW_PUBLISHER_NAME,
        issn: str | None = None,
    ) -> "ArticleScenario":
        self._journal_title = title
        self._eissn = eissn
        self._publisher_name = publisher
        self._issn = issn
        return self

    def without_journal(self) -> "ArticleScenario":
        self._journal_title = ""
        self._eissn = None
        self._publisher_name = None
        self._issn = None
        return self

    def _build_metadata(self) -> ExternalPublicationMetadata:
        journal: ExternalJournal | None = None
        if self._eissn is not None or self._issn is not None:
            journal = ExternalJournal(
                title=self._journal_title,
                issn=self._issn,
                eissn=self._eissn,
            )

        authors = [ExternalAuthor(name=a[0], affiliation=a[1], orcid=a[2]) for a in self._authors]
        return article_metadata(
            title=self._title,
            authors=authors,
            publisher=self._publisher_name,
            journal=journal,
            online_publication_date=self._online_publication_date,
            print_publication_date=self._print_publication_date,
            license=self._license,
            funding=[
                ExternalFundingMetadata(
                    funder=ExternalFundingOrganisationMetadata(
                        name=f[0], identifiers=[str(f[2])] if f[2] else []
                    ),
                    project_id=f[1] or "",
                )
                for f in self._funding
            ],
        )

    def setup_db(self) -> "ArticleScenario":
        if self._has_error:
            self.setup_client()
            return self

        if self._publisher_name is None:
            self.setup_client()
            return self

        publisher_id = publisher_services.create(self._publisher_name)
        if self._eissn is not None:
            self._journal_id = int(
                journal_services.create(
                    title=NonEmptyStr(self._journal_title),
                    eissn=Issn(self._eissn),
                    publisher_id=publisher_id,
                )
            )

        self._funder_lookup = {
            funding[0]: FundingOrganizationId(modelfactory.funding_organization(funding[0]).pk)
            for funding in self._funding
        }

        self.setup_client()
        return self

    def get_expected_fundingrequest(self) -> FundingRequest[Publication]:
        if self._has_error:
            raise RuntimeError("Scenario configured with error, it has no expected result")
        if self._journal_id is None:
            raise RuntimeError("setup_db() must be called before get_expected_fundingrequest()")

        expected_authors = [
            Author.new(
                name=NonEmptyStr(a[0]),
                orcid=orcid.Orcid(a[2]) if a[2] else None,
                affiliation=None,
                role=Role.CO_AUTHOR,
            )
            for a in self._authors
        ]
        expected_publication = Publication.new(
            title=NonEmptyStr(self._title),
            journal=JournalId(self._journal_id),
            relevant_authors=expected_authors,
            other_authors=AuthorNames(),
            license=License.Unknown,
            subject_area=UnknownConcept,
            publication_type=UnknownConcept,
            open_access_type=OpenAccessType.Unknown,
            publication_state=Published(
                online=self._online_publication_date,
                print=self._print_publication_date,
            ),
            links={self.doi},
        )
        expected_publication.contracts = ()

        return FundingRequest.new(
            publication=expected_publication,
            estimated_cost=Payment(
                amount=Money("0.00", Currency.EUR),
                method=PaymentMethod.Unknown,
                external_costsplitting=None,
            ),
            external_funding=[
                ExternalFunding(self._funder_lookup[f[0]], f[1] or "", "") for f in self._funding
            ],
            extra_contact=NoContact,
            request_remarks="",
        )


class BookScenario(_BaseScenario):
    """Scenario for importing a book (monograph) via DOI. Auto-derives expected FundingRequest."""

    def __init__(
        self, client: InMemoryDOIMetadataClient | None = None, doi: str = "10.1234/book.test"
    ) -> None:
        super().__init__(doi, client)
        self._publisher_id: int | None = None
        self._title = "Test Book"
        self._publisher_name: str | None = "Test Book Publisher"
        self._isbn = "978-3-16-148410-0"
        self._has_error = False

    @property
    def doi(self) -> Doi:
        return Doi(self._doi_str)

    @property
    def client(self) -> DOIMetadataClient:
        return self._client

    def with_isbn(self, isbn: str) -> "BookScenario":
        self._isbn = isbn
        return self

    def _build_metadata(self) -> ExternalPublicationMetadata:
        return book_metadata(
            title=self._title,
            publisher=self._publisher_name,
            isbn=self._isbn,
            print_publication_date=self._print_publication_date,
            funding=[
                ExternalFundingMetadata(
                    funder=ExternalFundingOrganisationMetadata(
                        name=f[0], identifiers=[str(f[2])] if f[2] else []
                    ),
                    project_id=f[1] or "",
                )
                for f in self._funding
            ],
        )

    def setup_db(self) -> "BookScenario":
        if self._has_error:
            self.setup_client()
            return self

        if self._publisher_name is None:
            self.setup_client()
            return self

        self._publisher_id = int(publisher_services.create(self._publisher_name))
        self.setup_client()
        return self

    def get_expected_fundingrequest(self) -> FundingRequest[Monograph]:
        if self._has_error:
            raise RuntimeError("Scenario configured with error, it has no expected result")
        if self._publisher_id is None:
            raise RuntimeError("setup_db() must be called before get_expected_fundingrequest()")

        expected_author = Author.new(
            name=NonEmptyStr("Test Author"),
            email="",
            orcid=None,
            affiliation=None,
            role=Role.CO_AUTHOR,
        )
        expected_monograph = Monograph.new(
            title=NonEmptyStr(self._title),
            publisher=PublisherId(self._publisher_id),
            relevant_authors=[expected_author],
            other_authors=AuthorNames(),
            license=License.Unknown,
            subject_area=UnknownConcept,
            publication_type=UnknownConcept,
            open_access_type=OpenAccessType.Unknown,
            publication_state=Published(
                online=None,
                print=self._print_publication_date,
            ),
            links={self.doi, Isbn(self._isbn)},
        )
        expected_monograph.contracts = ()

        return FundingRequest.new(
            publication=expected_monograph,
            estimated_cost=Payment(
                amount=Money("0.00", Currency.EUR),
                method=PaymentMethod.Unknown,
                external_costsplitting=None,
            ),
            external_funding=[],
            extra_contact=NoContact,
            request_remarks="",
        )
