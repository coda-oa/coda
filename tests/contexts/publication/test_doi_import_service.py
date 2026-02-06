"""Tests for DOI Import Service (Outside-In).

These tests verify the complete flow from DOI → FundingRequest with pre-populated Publication.
Tests are parametrized to run with both fake and real Crossref clients.
"""

import datetime
from collections.abc import Callable

import pytest
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq

from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.contexts.publication.services.doi_client import (
    CrossrefDoiClient,
    DOIMetadataClient,
    FakeDOIMetadataClient,
)
from coda.contexts.publication.services.doi_import_service import DOIImportService
from coda.domain.author import Author, Role
from coda.domain.fundingrequest import FundingRequest, Payment, PaymentMethod
from coda.domain.fundingrequest.fundingrequest import AnyFundingRequest
from coda.domain.money import Currency, Money
from coda.domain.publication import Authors, JournalId, License, Publication, Published
from coda.domain.publication.publication import Unpublished, UnpublishedState
from coda.domain.publication.links import Doi
from coda.domain.string import NonEmptyStr


def make_test_metadata(
    *,
    doi: str = "10.1234/test",
    title: str = "Test Article",
    authors: list[ExternalAuthor] | None = None,
    journal: ExternalJournal | None = None,
    publisher: str | None = "Test Publisher",
    license: str | None = None,
    online_publication_date: datetime.date | None = datetime.date(2024, 1, 1),
    print_publication_date: datetime.date | None = None,
    publication_type: str = "journal-article",
) -> tuple[FakeDOIMetadataClient, Doi]:
    """Create test metadata with sensible defaults and return configured client + DOI.

    Args:
        doi: DOI string for the test article
        title: Article title
        authors: List of authors (defaults to single author "Test Author")
        journal: Journal metadata (defaults to Nature-like journal)
        publisher: Publisher name (defaults to "Test Publisher", or None if journal is None)
        license: License string (defaults to None)
        online_publication_date: Online publication date (defaults to 2024-01-01)
        print_publication_date: Print publication date (defaults to None)
        publication_type: Publication type (defaults to "journal-article")

    Returns:
        Tuple of (configured FakeDOIMetadataClient, Doi object)
    """
    if authors is None:
        authors = [ExternalAuthor(name="Test Author")]

    # Default journal only if not explicitly set to None
    if journal is None and publication_type == "journal-article":
        journal = ExternalJournal(title="Nature", eissn="1476-4687")

    # If journal is None (e.g., books), publisher should also default to None
    if journal is None and publisher == "Test Publisher":
        publisher = None

    metadata = ExternalPublicationMetadata(
        title=title,
        authors=authors,
        publication_type=publication_type,
        journal=journal,
        publisher=publisher,
        license=license,
        online_publication_date=online_publication_date,
        print_publication_date=print_publication_date,
    )

    fake_client = FakeDOIMetadataClient()
    fake_client._data[doi] = metadata

    return fake_client, Doi(doi)


def get_publication_from_funding_request(
    funding_request: FundingRequest[Publication],
) -> Publication:
    """Extract and validate publication from funding request.

    Args:
        funding_request: The funding request to extract publication from

    Returns:
        The publication instance

    Raises:
        AssertionError: If publication is not a Publication instance
    """
    publication = funding_request.publication
    assert isinstance(publication, Publication)
    return publication


@pytest.fixture
def fake_doi_client() -> DOIMetadataClient:
    """Provides a fake DOI client for unit tests."""
    return FakeDOIMetadataClient()


@pytest.fixture
def real_doi_client() -> DOIMetadataClient:
    """Provides a real Crossref client for integration tests."""
    return CrossrefDoiClient(timeout=30.0)


def make_expected_funding_request_for_fake_nature_article(
    journal_id: int,
) -> FundingRequest[Publication]:
    """Factory for expected FundingRequest with fake DOI metadata."""
    doi = Doi("10.1038/nature12373")

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
    doi = Doi("10.1038/nature12373")

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
        license=License.Unknown,  # Real Crossref returns non-standard license URL
        publication_state=Published(
            online=datetime.date(2013, 7, 31),  # Crossref published-online
            print=datetime.date(2013, 8, 1),  # Crossref published-print
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


@pytest.fixture
def springer_nature_publisher(db: None) -> Publisher:
    """Creates Springer Nature publisher in database."""
    return Publisher.objects.create(name="Springer Nature")


@pytest.fixture
def nature_journal(springer_nature_publisher: Publisher) -> Journal:
    """Creates Nature journal in database."""
    return Journal.objects.create(
        title="Nature",
        eissn="1476-4687",
        publisher=springer_nature_publisher,
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
    nature_journal: Journal,
) -> None:
    """Given a valid DOI for a journal article, returns FundingRequest with Publication.

    The Publication should contain:
    - Title from DOI metadata
    - Authors from DOI metadata (all as CO_AUTHOR)
    - Journal matched by E-ISSN
    - License mapped from metadata
    - Publication state = Published with date
    - DOI link included

    The FundingRequest should have:
    - Estimated cost = Money(0, EUR)
    - Review status = Open
    - No external funding
    - No extra contact
    """
    doi_client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    doi_service = DOIImportService(doi_client=doi_client)

    doi = Doi("10.1038/nature12373")

    actual = doi_service.import_from_doi(doi)

    expected = get_expected_request(nature_journal.pk)

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
    # Get the DOI client fixture (fake or real)
    doi_client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    doi_service = DOIImportService(doi_client=doi_client)

    # Verify journal doesn't exist
    assert not Journal.objects.filter(eissn="1476-4687").exists()

    doi = Doi("10.1038/nature12373")

    funding_request = doi_service.import_from_doi(doi)

    # Verify journal was auto-created
    created_journal = Journal.objects.get(eissn="1476-4687")
    assert created_journal.title == "Nature"
    assert created_journal.eissn == "1476-4687"
    assert created_journal.publisher is not None  # Publisher was matched or created

    # Verify publication references the new journal
    publication = funding_request.publication
    assert isinstance(publication, Publication)
    assert publication.journal == created_journal.pk


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
    nature_journal: Journal,
) -> None:
    """Given a DOI with E-ISSN that exists in database, does NOT create/match publisher.

    This verifies that when the journal already exists, we:
    - Use the existing journal (with its existing publisher)
    - Do NOT call _match_or_create_publisher()
    - Do NOT create any new publishers
    """
    # Get the DOI client fixture (fake or real)
    doi_client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    doi_service = DOIImportService(doi_client=doi_client)

    # Count publishers before import
    publisher_count_before = Publisher.objects.count()

    # The nature_journal fixture has eissn="1476-4687" which matches the DOI metadata
    doi = Doi("10.1038/nature12373")

    funding_request = doi_service.import_from_doi(doi)

    # Verify no new publishers were created
    publisher_count_after = Publisher.objects.count()
    assert (
        publisher_count_after == publisher_count_before
    ), "Should not create publisher when journal already exists"

    # Verify we used the existing journal
    publication = funding_request.publication
    assert isinstance(publication, Publication)
    assert publication.journal == nature_journal.pk


@pytest.mark.django_db
def test__import_from_doi__metadata_without_journal__raises_assertion_error() -> None:
    """Given DOI metadata without journal (e.g., book/monograph), raises AssertionError.

    This documents the current limitation: we only support journal articles.
    When we add monograph support, this test should be updated.
    """
    fake_client, doi = make_test_metadata(
        doi="10.1234/book.123",
        title="Example Book Title",
        journal=None,  # Books don't have journals
        publication_type="book",
    )

    doi_service = DOIImportService(doi_client=fake_client)

    with pytest.raises(AssertionError, match="Journal articles must have journal metadata"):
        doi_service.import_from_doi(doi)


@pytest.mark.django_db
def test__import_from_doi__journal_without_eissn__raises_assertion_error() -> None:
    """Given journal metadata without E-ISSN, raises AssertionError.

    This documents the current limitation: we require E-ISSN for journal matching.
    When we add ISSN-only support, this test should be updated.
    """
    fake_client, doi = make_test_metadata(
        doi="10.1234/article.456",
        title="Article in Print-Only Journal",
        journal=ExternalJournal(
            title="Print-Only Journal",
            issn="1234-5678",  # Has print ISSN
            eissn=None,  # No E-ISSN
        ),
    )

    doi_service = DOIImportService(doi_client=fake_client)

    with pytest.raises(AssertionError, match="Journal must have E-ISSN"):
        doi_service.import_from_doi(doi)


@pytest.mark.django_db
def test__import_from_doi__metadata_without_publisher__raises_assertion_error() -> None:
    """Given metadata without publisher information, raises AssertionError.

    This documents the current limitation: we require publisher for journal creation.
    When we add support for publisher-less journals, this test should be updated.
    """
    fake_client, doi = make_test_metadata(
        doi="10.1234/article.789",
        title="Article Without Publisher Info",
        journal=ExternalJournal(title="Independent Journal", eissn="9876-5434"),
        publisher=None,  # No publisher information
    )

    doi_service = DOIImportService(doi_client=fake_client)

    with pytest.raises(AssertionError, match="Journal must have publisher"):
        doi_service.import_from_doi(doi)


@pytest.mark.django_db
def test__import_from_doi__invalid_license_string__returns_unknown_license(
    nature_journal: Journal,
) -> None:
    """Given metadata with invalid/unmappable license string, returns License.Unknown.

    This verifies that we gracefully handle license strings that don't map to CODA's
    License enum by returning License.Unknown instead of raising an exception.
    """
    fake_client, doi = make_test_metadata(
        doi="10.1234/invalid-license",
        title="Article with Invalid License",
        license="INVALID-LICENSE-XYZ",  # Invalid license that won't map
        publisher="Springer Nature",
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert publication.license == License.Unknown


@pytest.mark.django_db
def test__import_from_doi__author_with_whitespace_name_and_affiliation__creates_unknown_author(
    nature_journal: Journal,
) -> None:
    """Given author with whitespace-only name but valid affiliation, creates 'Unknown' author.

    This ensures we don't lose author information when name is missing but we have
    affiliation or ROR ID data.
    """
    fake_client, doi = make_test_metadata(
        doi="10.1234/whitespace-author",
        title="Article with Anonymous Author",
        authors=[
            ExternalAuthor(
                name="   ",  # Whitespace-only name
                affiliation="Massachusetts Institute of Technology",
                ror_id=None,
            )
        ],
        publisher="Springer Nature",
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert len(publication.relevant_authors) == 1
    assert publication.relevant_authors[0].name == "Unknown"


@pytest.mark.django_db
def test__import_from_doi__author_with_empty_name_and_ror_id__creates_unknown_author(
    nature_journal: Journal,
) -> None:
    """Given author with empty name but valid ROR ID, creates 'Unknown' author."""
    fake_client, doi = make_test_metadata(
        doi="10.1234/ror-only-author",
        title="Article with ROR-Only Author",
        authors=[
            ExternalAuthor(
                name="",  # Empty name
                affiliation=None,
                ror_id="https://ror.org/042nb2s44",  # MIT ROR ID
            )
        ],
        publisher="Springer Nature",
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert len(publication.relevant_authors) == 1
    assert publication.relevant_authors[0].name == "Unknown"


@pytest.mark.django_db
def test__import_from_doi__author_with_empty_name_and_no_data__skips_author(
    nature_journal: Journal,
) -> None:
    """Given author with empty name and no other data, skips creating the author entirely."""
    fake_client, doi = make_test_metadata(
        doi="10.1234/empty-author",
        title="Article with Empty Author",
        authors=[
            ExternalAuthor(
                name="",  # Empty name
                affiliation=None,  # No affiliation
                ror_id=None,  # No ROR ID
            )
        ],
        publisher="Springer Nature",
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert len(publication.relevant_authors) == 0


@pytest.mark.django_db
def test__import_from_doi__mixed_authors__creates_valid_and_unknown_skips_empty(
    nature_journal: Journal,
) -> None:
    """Given mixed author data, creates valid authors, uses 'Unknown' for partial data, skips empty.

    Tests the complete author validation logic:
    - Valid name → create with that name
    - Empty name + other data → create as "Unknown"
    - Empty name + no data → skip entirely
    """
    fake_client, doi = make_test_metadata(
        doi="10.1234/mixed-authors",
        title="Article with Mixed Authors",
        authors=[
            ExternalAuthor(name="John Doe", affiliation="MIT", ror_id=None),  # Valid
            ExternalAuthor(
                name="  ", affiliation="Harvard", ror_id=None
            ),  # Unknown (has affiliation)
            ExternalAuthor(name="", affiliation=None, ror_id=None),  # Skip (no data)
            ExternalAuthor(name="Jane Smith", affiliation=None, ror_id=None),  # Valid
        ],
        publisher="Springer Nature",
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

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
    fake_client, doi = make_test_metadata(
        doi="10.1234/whitespace-publisher",
        title="Article with Whitespace Publisher",
        journal=ExternalJournal(title="Test Journal", eissn="1234-5679"),
        publisher="  Springer Nature  ",  # Leading/trailing whitespace
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

    # Verify publisher created with trimmed name (no whitespace)
    created_publisher = Publisher.objects.get(name="Springer Nature")
    assert created_publisher.name == "Springer Nature"

    # Verify journal references the correctly-named publisher
    publication = get_publication_from_funding_request(funding_request)
    created_journal = Journal.objects.get(pk=publication.journal)
    assert created_journal.publisher.name == "Springer Nature"


@pytest.mark.django_db
def test__import_from_doi__no_publication_date__sets_unpublished_state(
    nature_journal: Journal,
) -> None:
    """Given metadata without publication date, sets publication state to Unpublished.

    When publication date is missing from DOI metadata:
    - Publication state should be Unpublished (not Published)
    - This allows importing articles that are accepted but not yet published
    """
    fake_client, doi = make_test_metadata(
        doi="10.1234/no-date",
        title="Article Without Publication Date",
        online_publication_date=None,  # No online date
        print_publication_date=None,  # No print date
        publisher="Springer Nature",
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Unpublished)
    assert publication.publication_state.state == UnpublishedState.Unknown


@pytest.mark.django_db
def test__import_from_doi__only_online_date__sets_published_with_online_date(
    nature_journal: Journal,
) -> None:
    """Given metadata with only online publication date, sets Published with online date."""
    online_date = datetime.date(2024, 6, 15)

    fake_client, doi = make_test_metadata(
        doi="10.1234/online-only",
        title="Article with Online Date Only",
        online_publication_date=online_date,
        print_publication_date=None,
        publisher="Springer Nature",
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Published)
    assert publication.publication_state.online == online_date
    assert publication.publication_state.print is None


@pytest.mark.django_db
def test__import_from_doi__only_print_date__sets_published_with_print_date(
    nature_journal: Journal,
) -> None:
    """Given metadata with only print publication date, sets Published with print date."""
    print_date = datetime.date(2024, 7, 1)

    fake_client, doi = make_test_metadata(
        doi="10.1234/print-only",
        title="Article with Print Date Only",
        online_publication_date=None,
        print_publication_date=print_date,
        publisher="Springer Nature",
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Published)
    assert publication.publication_state.online is None
    assert publication.publication_state.print == print_date


@pytest.mark.django_db
def test__import_from_doi__both_dates__sets_published_with_both_dates(
    nature_journal: Journal,
) -> None:
    """Given metadata with both online and print dates, sets Published with both dates."""
    online_date = datetime.date(2024, 5, 1)
    print_date = datetime.date(2024, 6, 1)

    fake_client, doi = make_test_metadata(
        doi="10.1234/both-dates",
        title="Article with Both Dates",
        online_publication_date=online_date,
        print_publication_date=print_date,
        publisher="Springer Nature",
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Published)
    assert publication.publication_state.online == online_date
    assert publication.publication_state.print == print_date
