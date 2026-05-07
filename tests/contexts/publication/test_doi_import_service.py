"""Tests for DOI Import Service (Outside-In).

These tests verify the complete flow from DOI → FundingRequest with pre-populated Publication.
Tests are parametrized to run with both fake and real Crossref clients.
"""

import datetime
from collections.abc import Callable

import pytest
from tests import domainfactory
from tests.contexts.publication import metadatafactory
from tests.contexts.publication.fixtures.doi_client import FakeDOIMetadataClient
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq

from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.journals import services as journal_services
from coda.apps.journals.models import Journal
from coda.apps.publications.repositories import publication_repository
from coda.apps.publishers import services as publisher_services
from coda.apps.publishers.models import Publisher
from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.contexts.publication.dto.preview import PreviewArticle, PreviewMonograph
from coda.contexts.publication.services.doi_client import CrossrefDoiClient, DOIMetadataClient
from coda.contexts.publication.services.doi_import_service import (
    DOIImportService,
    OverrideImportAsArticle,
    OverrideImportAsMonograph,
)
from coda.contexts.publication.services.errors import DOIAlreadyImported, InvalidMetadataError
from coda.domain.author import Author, Role
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest, FundingRequestId, Payment, PaymentMethod
from coda.domain.fundingrequest.fundingrequest import AnyFundingRequest
from coda.domain.issn import Issn
from coda.domain.money import Currency, Money
from coda.domain.publication import (
    Authors,
    JournalId,
    License,
    Monograph,
    Publication,
    Published,
    Unpublished,
    UnpublishedState,
)
from coda.domain.publication.links import Doi, Isbn
from coda.domain.string import NonEmptyStr

# Test data constants
NATURE_DOI = "10.1038/nature12373"
NATURE_EISSN = metadatafactory.NATURE_EISSN
NATURE_JOURNAL_TITLE = metadatafactory.NATURE_JOURNAL_TITLE
SPRINGER_NATURE_PUBLISHER = "Springer Nature"
SPRINGER_NATURE_REAL_PUBLISHER = "Springer Science and Business Media LLC"

SPRINGER_BOOK_DOI = "10.1007/978-3-319-18938-3"
SPRINGER_BOOK_ISBN = "9783319189376"  # Print ISBN (first in Crossref array)
SPRINGER_BOOK_TITLE = "Quantum Microscopy of Biological Systems"
SPRINGER_BOOK_PUBLISHER = "Springer International Publishing"


def _make_client(doi: str, metadata: "ExternalPublicationMetadata") -> FakeDOIMetadataClient:
    client = FakeDOIMetadataClient()
    client.data[doi] = metadata
    return client


def make_article_metadata(
    *,
    doi: str = "10.1234/test",
    **kwargs: object,
) -> tuple[FakeDOIMetadataClient, Doi]:
    """Build article metadata and return a configured (client, Doi) pair.

    All keyword arguments are forwarded to metadatafactory.article_metadata().
    """
    from tests.contexts.publication.metadatafactory import article_metadata  # noqa: PLC0415

    metadata = article_metadata(**kwargs)  # type: ignore[arg-type]
    return _make_client(doi, metadata), Doi(doi)


def make_book_metadata(
    *,
    doi: str = "10.1234/test-book",
    **kwargs: object,
) -> tuple[FakeDOIMetadataClient, Doi]:
    """Build book metadata and return a configured (client, Doi) pair.

    All keyword arguments are forwarded to metadatafactory.book_metadata().
    """
    from tests.contexts.publication.metadatafactory import book_metadata  # noqa: PLC0415

    metadata = book_metadata(**kwargs)  # type: ignore[arg-type]
    return _make_client(doi, metadata), Doi(doi)


def get_publication_from_funding_request(
    funding_request_id: FundingRequestId,
) -> Publication:
    """Extract and validate publication from funding request in database.

    Args:
        funding_request_id: The ID of the funding request

    Returns:
        The publication instance

    Raises:
        AssertionError: If publication is not a Publication instance
    """
    funding_request = fundingrequest_repository.get_by_id(funding_request_id)
    publication = funding_request.publication
    assert isinstance(publication, Publication)
    return publication


def create_springer_nature_journal() -> int:
    """Create Springer Nature publisher and Nature journal in database using services.

    Returns:
        The integer ID of the created Nature journal
    """
    publisher_id = publisher_services.create(SPRINGER_NATURE_PUBLISHER)
    journal_id = journal_services.create(
        title=NonEmptyStr(NATURE_JOURNAL_TITLE),
        eissn=Issn(NATURE_EISSN),
        publisher_id=publisher_id,
    )
    return int(journal_id)


def create_springer_book_publisher() -> int:
    """Create Springer International Publishing publisher in database.

    Returns:
        The integer ID of the created publisher
    """
    publisher_id = publisher_services.create(SPRINGER_BOOK_PUBLISHER)
    return int(publisher_id)


@pytest.fixture
def fake_doi_client() -> DOIMetadataClient:
    """Provides a fake DOI client configured with test data."""
    from tests.contexts.publication.fixtures.test_metadata import (
        nature_article_metadata,
        springer_book_metadata,
    )

    client = FakeDOIMetadataClient()
    # Configure with test data
    client.data[NATURE_DOI] = nature_article_metadata()
    client.data[SPRINGER_BOOK_DOI] = springer_book_metadata()
    return client


@pytest.fixture
def real_doi_client() -> DOIMetadataClient:
    """Provides a real Crossref client for integration tests."""
    return CrossrefDoiClient(timeout=30.0)


def make_expected_funding_request_for_fake_nature_article(
    journal_id: int,
) -> FundingRequest[Publication]:
    """Factory for expected FundingRequest with fake DOI metadata."""
    doi = Doi(NATURE_DOI)

    expected_authors = Authors(
        [
            Author.new(name=NonEmptyStr("John Doe"), role=Role.CO_AUTHOR),
            Author.new(name=NonEmptyStr("Jane Smith"), role=Role.CO_AUTHOR),
        ]
    )

    expected_publication = Publication.new(
        title=NonEmptyStr("Example Nature Article"),
        journal=JournalId(journal_id),
        relevant_authors=expected_authors,
        license=License.CC_BY,
        publication_state=Published(online=datetime.date(2024, 1, 15)),
        links={doi},
    )

    return FundingRequest.new(
        publication=expected_publication,
        estimated_cost=Payment(
            amount=Money(0, Currency.EUR),
            method=PaymentMethod.Unknown,
        ),
    )


def make_expected_funding_request_for_real_nature_article(
    journal_id: int,
) -> FundingRequest[Publication]:
    """Factory for expected FundingRequest with real Crossref metadata."""
    doi = Doi(NATURE_DOI)

    # Real Crossref data for this DOI (abbreviated author names)
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
        journal=JournalId(journal_id),
        relevant_authors=expected_authors,
        # NOTE: Real Crossref returns non-standard license URL
        license=License.Unknown,
        publication_state=Published(
            online=datetime.date(2013, 7, 31),
            print=datetime.date(2013, 8, 1),
        ),
        links={doi},
    )

    return FundingRequest.new(
        publication=expected_publication,
        estimated_cost=Payment(
            amount=Money(0, Currency.EUR),
            method=PaymentMethod.Unknown,
        ),
    )


def make_expected_funding_request_for_fake_springer_book(
    publisher_id: int,
) -> FundingRequest[Monograph]:
    """Factory for expected FundingRequest for a book with fake DOI metadata."""
    doi = Doi(SPRINGER_BOOK_DOI)
    isbn = Isbn(SPRINGER_BOOK_ISBN)

    expected_authors = Authors(
        [
            Author.new(name=NonEmptyStr("Michael Taylor"), role=Role.CO_AUTHOR),
        ]
    )

    expected_monograph = Monograph.new(
        title=NonEmptyStr(SPRINGER_BOOK_TITLE),
        publisher=PublisherId(publisher_id),
        relevant_authors=expected_authors,
        license=License.Unknown,
        publication_state=Published(print=datetime.date(2015, 1, 1)),
        links={doi, isbn},
    )

    return FundingRequest.new(
        publication=expected_monograph,
        estimated_cost=Payment(
            amount=Money(0, Currency.EUR),
            method=PaymentMethod.Unknown,
        ),
    )


def make_expected_funding_request_for_real_springer_book(
    publisher_id: int,
) -> FundingRequest[Monograph]:
    """Factory for expected FundingRequest for a book with real Crossref metadata."""
    doi = Doi(SPRINGER_BOOK_DOI)
    isbn = Isbn(SPRINGER_BOOK_ISBN)

    expected_authors = Authors(
        [
            Author.new(name=NonEmptyStr("Michael Taylor"), role=Role.CO_AUTHOR),
        ]
    )

    expected_monograph = Monograph.new(
        title=NonEmptyStr(SPRINGER_BOOK_TITLE),
        publisher=PublisherId(publisher_id),
        relevant_authors=expected_authors,
        # Real Crossref data has TDM license, which we map to Unknown
        license=License.Unknown,
        publication_state=Published(print=datetime.date(2015, 1, 1)),
        links={doi, isbn},
    )

    return FundingRequest.new(
        publication=expected_monograph,
        estimated_cost=Payment(
            amount=Money(0, Currency.EUR),
            method=PaymentMethod.Unknown,
        ),
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("client_fixture", "get_expected_request"),
    [
        ("fake_doi_client", make_expected_funding_request_for_fake_nature_article),
        pytest.param(
            "real_doi_client",
            make_expected_funding_request_for_real_nature_article,
            marks=pytest.mark.integration,
        ),
    ],
)
def test__import_from_doi__valid_journal_article_doi__returns_funding_request_with_populated_publication(
    client_fixture: str,
    get_expected_request: Callable[[int], AnyFundingRequest],
    request: pytest.FixtureRequest,
) -> None:
    """Given a valid DOI for a journal article, creates and returns FundingRequestId.

    The created FundingRequest in database should contain:
    - Publication with title from DOI metadata
    - Authors from DOI metadata (all as CO_AUTHOR)
    - Journal matched by E-ISSN
    - License mapped from metadata
    - Publication state = Published with date
    - DOI link included
    - Estimated cost = Money(0, EUR)
    - Review status = Open
    - No external funding
    - No extra contact
    """
    journal_id = create_springer_nature_journal()
    doi = Doi(NATURE_DOI)
    doi_client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    sut = DOIImportService(doi_client=doi_client)

    funding_request_id = sut.import_from_doi(doi)

    actual = fundingrequest_repository.get_by_id(funding_request_id)
    expected = get_expected_request(journal_id)
    assert_fundingrequest_eq(actual, expected)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("client_fixture", "get_expected_request"),
    [
        ("fake_doi_client", make_expected_funding_request_for_fake_springer_book),
        pytest.param(
            "real_doi_client",
            make_expected_funding_request_for_real_springer_book,
            marks=pytest.mark.integration,
        ),
    ],
)
def test__import_from_doi__valid_book_doi__returns_funding_request_with_populated_monograph(
    client_fixture: str,
    get_expected_request: Callable[[int], AnyFundingRequest],
    request: pytest.FixtureRequest,
) -> None:
    """Given a valid DOI for a book, creates and returns FundingRequestId with Monograph.

    The created FundingRequest in database should contain:
    - Monograph with title from DOI metadata
    - Authors from DOI metadata (all as CO_AUTHOR)
    - Publisher matched by name (or created if not found)
    - License mapped from metadata
    - Publication state = Published with date
    - DOI link included
    - Estimated cost = Money(0, EUR)
    - Review status = Open
    - No external funding
    - No extra contact
    """
    publisher_id = create_springer_book_publisher()
    doi = Doi(SPRINGER_BOOK_DOI)
    doi_client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    sut = DOIImportService(doi_client=doi_client)

    funding_request_id = sut.import_from_doi(doi)

    actual = fundingrequest_repository.get_by_id(funding_request_id)
    expected = get_expected_request(publisher_id)
    assert_fundingrequest_eq(actual, expected)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_doi_client",
        pytest.param("real_doi_client", marks=pytest.mark.integration),
    ],
)
def test__import_from_doi__journal_not_in_database__auto_creates_journal(
    client_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    """Given a DOI with E-ISSN not in database, automatically creates the journal.

    The new journal should be created with:
    - Title from DOI metadata
    - E-ISSN from DOI metadata
    - Publisher matched by name (or created if not found)
    """
    doi_client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    sut = DOIImportService(doi_client=doi_client)

    doi = Doi(NATURE_DOI)

    sut.import_from_doi(doi)

    created_journal = journal_services.find_by_eissn(Issn(NATURE_EISSN))
    assert created_journal is not None
    assert created_journal.title == NATURE_JOURNAL_TITLE
    assert created_journal.eissn == NATURE_EISSN

    assert created_journal.publisher is not None
    assert created_journal.publisher.name == SPRINGER_NATURE_REAL_PUBLISHER


@pytest.mark.django_db
@pytest.mark.parametrize(
    "client_fixture",
    [
        "fake_doi_client",
        pytest.param("real_doi_client", marks=pytest.mark.integration),
    ],
)
def test__import_from_doi__journal_exists_in_database__does_not_create_publisher(
    client_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    """Given a DOI with E-ISSN that exists in database, does NOT create/match publisher.

    This verifies that when the journal already exists, we:
    - Use the existing journal (with its existing publisher)
    - Do NOT call _match_or_create_publisher()
    - Do NOT create any new publishers
    """
    publisher_id = publisher_services.create(SPRINGER_NATURE_PUBLISHER)
    journal_id = journal_services.create(
        title=NonEmptyStr(NATURE_JOURNAL_TITLE),
        eissn=Issn(NATURE_EISSN),
        publisher_id=publisher_id,
    )
    doi_client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    sut = DOIImportService(doi_client=doi_client)
    doi = Doi(NATURE_DOI)

    funding_request_id = sut.import_from_doi(doi)

    assert Journal.objects.count() == 1
    assert Publisher.objects.count() == 1
    funding_request = fundingrequest_repository.get_by_id(funding_request_id)
    publication = funding_request.publication
    assert isinstance(publication, Publication)
    assert publication.journal == journal_id


@pytest.mark.django_db
def test__import_from_doi__metadata_without_journal__raises_invalid_metadata_error() -> None:
    """Given book/monograph metadata without publisher, raises InvalidMetadataError.

    Monographs are now supported, but require a publisher name.
    """
    fake_client, doi = make_article_metadata(
        journal=None,
        publication_type="book",
        publisher=None,
    )

    sut = DOIImportService(doi_client=fake_client)

    with pytest.raises(InvalidMetadataError, match="Monograph missing publisher name"):
        sut.import_from_doi(doi)


@pytest.mark.django_db
def test__import_from_doi__journal_without_eissn__raises_invalid_metadata_error() -> None:
    """Given journal metadata without E-ISSN, raises InvalidMetadataError.

    This documents the current limitation: we require E-ISSN for journal matching.
    When we add ISSN-only support, this test should be updated.
    """
    fake_client, doi = make_article_metadata(
        journal=ExternalJournal(
            title="Print-Only Journal",
            issn="1234-5678",
            eissn=None,
        ),
    )

    sut = DOIImportService(doi_client=fake_client)

    with pytest.raises(InvalidMetadataError, match="Journal 'Print-Only Journal' missing E-ISSN"):
        sut.import_from_doi(doi)


@pytest.mark.django_db
def test__import_from_doi__metadata_without_publisher__raises_invalid_metadata_error() -> None:
    """Given metadata without publisher information, raises InvalidMetadataError.

    This documents the current limitation: we require publisher for journal creation.
    When we add support for publisher-less journals, this test should be updated.
    """
    fake_client, doi = make_article_metadata(
        journal=ExternalJournal(title="Independent Journal", eissn="9876-5434"),
        publisher=None,
    )

    sut = DOIImportService(doi_client=fake_client)

    with pytest.raises(InvalidMetadataError, match="Journal missing publisher name"):
        sut.import_from_doi(doi)


@pytest.mark.django_db
def test__import_from_doi__invalid_license_string__returns_unknown_license() -> None:
    """Given metadata with invalid/unmappable license string, returns License.Unknown.

    This verifies that we gracefully handle license strings that don't map to CODA's
    License enum by returning License.Unknown instead of raising an exception.
    """
    create_springer_nature_journal()

    fake_client, doi = make_article_metadata(
        license="INVALID-LICENSE-XYZ",
        publisher=SPRINGER_NATURE_PUBLISHER,
    )

    sut = DOIImportService(doi_client=fake_client)
    funding_request = sut.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert publication.license == License.Unknown


@pytest.mark.django_db
def test__import_from_doi__author_with_whitespace_name_and_affiliation__creates_unknown_author() -> (
    None
):
    """Given author with whitespace-only name but valid affiliation, creates 'Unknown' author.

    This ensures we don't lose author information when name is missing but we have
    affiliation or ROR ID data.
    """
    create_springer_nature_journal()

    fake_client, doi = make_article_metadata(
        authors=[
            ExternalAuthor(
                name="   ",
                affiliation="Massachusetts Institute of Technology",
                ror_id=None,
            )
        ],
        publisher=SPRINGER_NATURE_PUBLISHER,
    )

    sut = DOIImportService(doi_client=fake_client)
    funding_request = sut.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert len(publication.relevant_authors) == 1
    assert publication.relevant_authors[0].name == "Unknown"


@pytest.mark.django_db
def test__import_from_doi__author_with_empty_name_and_ror_id__creates_unknown_author() -> None:
    """Given author with empty name but valid ROR ID, creates 'Unknown' author."""
    create_springer_nature_journal()

    empty_name = ""
    mit_ror_id = "https://ror.org/042nb2s44"

    fake_client, doi = make_article_metadata(
        authors=[
            ExternalAuthor(
                name=empty_name,
                affiliation=None,
                ror_id=mit_ror_id,
            )
        ],
        publisher=SPRINGER_NATURE_PUBLISHER,
    )

    sut = DOIImportService(doi_client=fake_client)
    funding_request = sut.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert len(publication.relevant_authors) == 1
    assert publication.relevant_authors[0].name == "Unknown"


@pytest.mark.django_db
def test__import_from_doi__author_with_empty_name_and_no_data__skips_author() -> None:
    """Given author with empty name and no other data, skips creating the author entirely."""
    create_springer_nature_journal()

    fake_client, doi = make_article_metadata(
        authors=[
            ExternalAuthor(
                name="",
                affiliation=None,
                ror_id=None,
            )
        ],
        publisher=SPRINGER_NATURE_PUBLISHER,
    )

    sut = DOIImportService(doi_client=fake_client)
    funding_request = sut.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert len(publication.relevant_authors) == 0


@pytest.mark.django_db
def test__import_from_doi__mixed_authors__creates_valid_and_unknown_skips_empty() -> None:
    """Given mixed author data, creates valid authors, uses 'Unknown' for partial data, skips empty.

    Tests the complete author validation logic:
    - Valid name → create with that name
    - Empty name + other data → create as "Unknown"
    - Empty name + no data → skip entirely
    """
    create_springer_nature_journal()

    author_with_valid_name = ExternalAuthor(name="John Doe", affiliation="MIT", ror_id=None)
    author_with_whitespace_name_but_affiliation = ExternalAuthor(
        name="  ", affiliation="Harvard", ror_id=None
    )
    author_with_no_name_and_no_data = ExternalAuthor(name="", affiliation=None, ror_id=None)
    another_author_with_valid_name = ExternalAuthor(
        name="Jane Smith", affiliation=None, ror_id=None
    )

    fake_client, doi = make_article_metadata(
        doi="10.1234/mixed-authors",
        title="Article with Mixed Authors",
        authors=[
            author_with_valid_name,
            author_with_whitespace_name_but_affiliation,
            author_with_no_name_and_no_data,
            another_author_with_valid_name,
        ],
        publisher=SPRINGER_NATURE_PUBLISHER,
    )
    sut = DOIImportService(doi_client=fake_client)

    funding_request = sut.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert len(publication.relevant_authors) == 3
    assert publication.relevant_authors[0].name == "John Doe"
    assert publication.relevant_authors[1].name == "Unknown"
    assert publication.relevant_authors[2].name == "Jane Smith"


@pytest.mark.django_db
def test__import_from_doi__publisher_with_whitespace__trims_publisher_name() -> None:
    """Given publisher name with leading/trailing whitespace, creates publisher with trimmed name.

    This prevents duplicate publishers that differ only by whitespace:
    - "Springer Nature" vs "  Springer Nature  "

    Publisher names should be trimmed before matching or creating.
    """
    publisher_with_whitespace = f"  {SPRINGER_NATURE_PUBLISHER}  "

    fake_client, doi = make_article_metadata(
        doi="10.1234/whitespace-publisher",
        title="Article with Whitespace Publisher",
        journal=ExternalJournal(title="Test Journal", eissn="1234-5679"),
        publisher=publisher_with_whitespace,
    )
    sut = DOIImportService(doi_client=fake_client)

    funding_request = sut.import_from_doi(doi)

    created_publisher = publisher_services.find_by_name(SPRINGER_NATURE_PUBLISHER)
    assert created_publisher is not None
    assert created_publisher.name == SPRINGER_NATURE_PUBLISHER

    publication = get_publication_from_funding_request(funding_request)
    created_journal = journal_services.get_by_pk(publication.journal)
    assert created_journal.publisher.name == SPRINGER_NATURE_PUBLISHER


@pytest.mark.django_db
def test__import_from_doi__no_publication_date__sets_unpublished_state() -> None:
    """Given metadata without publication date, sets publication state to Unpublished.

    When publication date is missing from DOI metadata:
    - Publication state should be Unpublished (not Published)
    - This allows importing articles that are accepted but not yet published
    """
    create_springer_nature_journal()

    fake_client, doi = make_article_metadata(
        doi="10.1234/no-date",
        title="Article Without Publication Date",
        online_publication_date=None,  # No online date
        print_publication_date=None,  # No print date
        publisher=SPRINGER_NATURE_PUBLISHER,
    )

    sut = DOIImportService(doi_client=fake_client)
    funding_request = sut.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Unpublished)
    assert publication.publication_state.state == UnpublishedState.Unknown


@pytest.mark.django_db
def test__import_from_doi__only_online_date__sets_published_with_online_date() -> None:
    """Given metadata with only online publication date, sets Published with online date."""
    create_springer_nature_journal()

    online_date = datetime.date(2024, 6, 15)

    fake_client, doi = make_article_metadata(
        doi="10.1234/online-only",
        title="Article with Online Date Only",
        online_publication_date=online_date,
        print_publication_date=None,
        publisher=SPRINGER_NATURE_PUBLISHER,
    )

    sut = DOIImportService(doi_client=fake_client)

    funding_request = sut.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Published)
    assert publication.publication_state.online == online_date
    assert publication.publication_state.print is None


@pytest.mark.django_db
def test__import_from_doi__only_print_date__sets_published_with_print_date() -> None:
    """Given metadata with only print publication date, sets Published with print date."""
    create_springer_nature_journal()

    print_date = datetime.date(2024, 7, 1)

    fake_client, doi = make_article_metadata(
        doi="10.1234/print-only",
        title="Article with Print Date Only",
        online_publication_date=None,
        print_publication_date=print_date,
        publisher=SPRINGER_NATURE_PUBLISHER,
    )

    sut = DOIImportService(doi_client=fake_client)
    funding_request = sut.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Published)
    assert publication.publication_state.online is None
    assert publication.publication_state.print == print_date


@pytest.mark.django_db
def test__import_from_doi__both_dates__sets_published_with_both_dates() -> None:
    """Given metadata with both online and print dates, sets Published with both dates."""
    create_springer_nature_journal()
    online_date = datetime.date(2024, 5, 1)
    print_date = datetime.date(2024, 6, 1)

    fake_client, doi = make_article_metadata(
        doi="10.1234/both-dates",
        title="Article with Both Dates",
        online_publication_date=online_date,
        print_publication_date=print_date,
        publisher=SPRINGER_NATURE_PUBLISHER,
    )
    sut = DOIImportService(doi_client=fake_client)

    funding_request = sut.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Published)
    assert publication.publication_state.online == online_date
    assert publication.publication_state.print == print_date


@pytest.mark.django_db
def test__import_from_doi__duplicate_doi__raises_doi_already_imported() -> None:
    """Test that importing a DOI that already exists raises DOIAlreadyImported."""
    journal_id = create_springer_nature_journal()
    doi = Doi("10.1038/nature12373")

    publication = domainfactory.publication(JournalId(journal_id))
    publication.links = {doi}
    publication_id = publication_repository.create(publication)

    fake_client = FakeDOIMetadataClient()
    sut = DOIImportService(fake_client)

    with pytest.raises(DOIAlreadyImported) as exc_info:
        sut.import_from_doi(doi)

    assert exc_info.value.doi == doi
    assert exc_info.value.publication_id == publication_id


@pytest.mark.django_db
def test__prepare_funding_request_dto__returns_dto_without_persisting() -> None:
    """Test that prepare_funding_request_dto returns DTO without creating database records."""
    create_springer_nature_journal()

    fake_client, doi = make_article_metadata(
        doi="10.1234/prepare-dto-test",
        title="Test DTO Preparation",
        authors=[ExternalAuthor(name="Test Author")],
        publisher=SPRINGER_NATURE_PUBLISHER,
    )

    sut = DOIImportService(fake_client)
    sut.fetch_doi_preview(doi)

    all_requests = fundingrequest_repository.all()
    assert len(all_requests) == 0


@pytest.mark.django_db
def test__prepare_funding_request_dto__article__does_not_create_journal_or_publisher() -> None:
    """Test that prepare_funding_request_dto does NOT create journals or publishers for articles.

    This is critical for preview workflows - we should only build the DTO without
    persisting any entities. Journal/publisher creation should happen during import_from_doi().
    """
    # Arrange - Verify database starts empty (no journals or publishers)
    assert Journal.objects.count() == 0
    assert Publisher.objects.count() == 0

    fake_client, doi = make_article_metadata()

    sut = DOIImportService(fake_client)

    # Act
    dto = sut.fetch_doi_preview(doi)

    # Assert - DTO should be created successfully
    assert dto is not None
    assert isinstance(dto.publication, PreviewArticle)

    # Assert - No database entities should be created
    assert Journal.objects.count() == 0, "prepare_funding_request_dto created a journal"
    assert Publisher.objects.count() == 0, "prepare_funding_request_dto created a publisher"
    assert (
        len(fundingrequest_repository.all()) == 0
    ), "prepare_funding_request_dto created a funding request"


@pytest.mark.django_db
def test__prepare_funding_request_dto__monograph__does_not_create_publisher() -> None:
    """Test that prepare_funding_request_dto does NOT create publishers for monographs.

    This is critical for preview workflows - we should only build the DTO without
    persisting any entities. Publisher creation should happen during import_from_doi().
    """
    # Arrange - Verify database starts empty
    assert Publisher.objects.count() == 0

    nonexistent_publisher = "New Academic Press"
    fake_client, doi = make_book_metadata(
        publisher=nonexistent_publisher,
    )

    sut = DOIImportService(fake_client)

    # Act
    dto = sut.fetch_doi_preview(doi)

    # Assert - DTO should be created successfully
    assert dto is not None
    assert isinstance(dto.publication, PreviewMonograph)

    # Assert - No database entities should be created
    assert Publisher.objects.count() == 0, "prepare_funding_request_dto created a publisher"
    assert (
        len(fundingrequest_repository.all()) == 0
    ), "prepare_funding_request_dto created a funding request"


@pytest.mark.django_db
def test__build_preview_with_type_override__to_article__uses_resolved_journal() -> None:
    """Overriding to article uses journal title and EISSN from the resolved DB journal."""
    fake_client, doi = make_article_metadata(doi="10.1234/test.article")
    publisher_id = publisher_services.create(name="Test Publisher")
    journal_id = journal_services.create(
        title=NonEmptyStr(NATURE_JOURNAL_TITLE),
        eissn=Issn(NATURE_EISSN),
        publisher_id=publisher_id,
    )

    service = DOIImportService(doi_client=fake_client)
    result = service.build_preview_with_type_override(
        doi, OverrideImportAsArticle(journal_id=journal_id)
    )

    assert isinstance(result.publication, PreviewArticle)
    assert result.publication.journal is not None
    assert result.publication.journal.title == NATURE_JOURNAL_TITLE
    assert result.publication.journal.eissn == NATURE_EISSN


@pytest.mark.django_db
def test__build_preview_with_type_override__to_monograph__uses_resolved_publisher() -> None:
    """Overriding to monograph uses publisher name from the resolved DB publisher."""
    fake_client, doi = make_article_metadata(doi="10.1234/test.article")
    publisher_id = publisher_services.create(name="Springer Nature")

    service = DOIImportService(doi_client=fake_client)
    result = service.build_preview_with_type_override(
        doi, OverrideImportAsMonograph(publisher_id=publisher_id)
    )

    assert isinstance(result.publication, PreviewMonograph)
    assert result.publication.publisher_name == "Springer Nature"
