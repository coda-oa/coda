"""Tests for DOI Import Service (Outside-In).

These tests verify the complete flow from DOI → FundingRequest with pre-populated Publication.
Tests are parametrized to run with both fake and real Crossref clients.
"""

import datetime
from collections.abc import Callable

import pytest
from tests import domainfactory
from tests.contexts.publication.fixtures.doi_client import FakeDOIMetadataClient
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq

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
from coda.contexts.publication.services.doi_client import (
    CrossrefDoiClient,
    DOIMetadataClient,
)
from coda.contexts.publication.services.doi_import_service import (
    DOIAlreadyImported,
    DOIImportService,
    InvalidMetadataError,
)
from coda.domain.author import Author, Role
from coda.domain.fundingrequest import FundingRequest, Payment, PaymentMethod
from coda.domain.fundingrequest.fundingrequest import AnyFundingRequest
from coda.domain.issn import Issn
from coda.domain.money import Currency, Money
from coda.domain.publication import (
    Authors,
    JournalId,
    License,
    Publication,
    Published,
    Unpublished,
    UnpublishedState,
)
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


def create_springer_nature_journal() -> int:
    """Create Springer Nature publisher and Nature journal in database using services.

    Returns:
        The integer ID of the created Nature journal
    """
    publisher_id = publisher_services.create("Springer Nature")
    journal_id = journal_services.create(
        title=NonEmptyStr("Nature"),
        eissn=Issn("1476-4687"),
        publisher_id=publisher_id,
    )
    return int(journal_id)


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
    # GIVEN: Database has existing publisher and journal matching the DOI metadata
    journal_id = create_springer_nature_journal()

    doi = Doi("10.1038/nature12373")
    doi_client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    doi_service = DOIImportService(doi_client=doi_client)

    # WHEN: Import from DOI
    actual = doi_service.import_from_doi(doi)

    # THEN: FundingRequest matches expected structure
    expected = get_expected_request(journal_id)
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
    # GIVEN: Database has no journals or publishers
    assert Journal.objects.count() == 0
    assert Publisher.objects.count() == 0

    doi_client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    doi_service = DOIImportService(doi_client=doi_client)

    expected_publisher_name = (
        "Springer Nature"
        if client_fixture == "fake_doi_client"
        else "Springer Science and Business Media LLC"
    )

    doi = Doi("10.1038/nature12373")

    # WHEN: Import from DOI
    funding_request = doi_service.import_from_doi(doi)

    # THEN: Journal and publisher were auto-created
    assert Journal.objects.count() == 1
    assert Publisher.objects.count() == 1

    # Verify created entities match DOI metadata
    created_journal = journal_services.find_by_eissn(Issn("1476-4687"))
    assert created_journal is not None
    assert created_journal.title == "Nature"
    assert created_journal.eissn == "1476-4687"

    created_publisher = publisher_services.find_by_name(expected_publisher_name)
    assert created_publisher is not None
    assert created_publisher.name == expected_publisher_name

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
) -> None:
    """Given a DOI with E-ISSN that exists in database, does NOT create/match publisher.

    This verifies that when the journal already exists, we:
    - Use the existing journal (with its existing publisher)
    - Do NOT call _match_or_create_publisher()
    - Do NOT create any new publishers
    """
    # GIVEN: Database has existing publisher and journal
    publisher_id = publisher_services.create("Springer Nature")
    journal_id = journal_services.create(
        title=NonEmptyStr("Nature"),
        eissn=Issn("1476-4687"),
        publisher_id=publisher_id,
    )

    assert Journal.objects.count() == 1
    assert Publisher.objects.count() == 1

    doi_client: DOIMetadataClient = request.getfixturevalue(client_fixture)
    doi_service = DOIImportService(doi_client=doi_client)

    # The DOI metadata has eissn="1476-4687" which matches existing journal
    doi = Doi("10.1038/nature12373")

    # WHEN: Import from DOI
    funding_request = doi_service.import_from_doi(doi)

    # THEN: No new publishers or journals were created
    assert Journal.objects.count() == 1
    assert Publisher.objects.count() == 1

    # AND: We used the existing journal
    publication = funding_request.publication
    assert isinstance(publication, Publication)
    assert publication.journal == int(journal_id)


@pytest.mark.django_db
def test__import_from_doi__metadata_without_journal__raises_invalid_metadata_error() -> None:
    """Given DOI metadata without journal (e.g., book/monograph), raises InvalidMetadataError.

    This documents the current limitation: we only support journal articles.
    When we add monograph support, this test should be updated.
    """
    fake_client, doi = make_test_metadata(
        doi="10.1234/book.123",
        title="Example Book Title",
        journal=None,
        publication_type="book",
    )

    doi_service = DOIImportService(doi_client=fake_client)

    with pytest.raises(InvalidMetadataError, match="Journal article missing journal metadata"):
        doi_service.import_from_doi(doi)


@pytest.mark.django_db
def test__import_from_doi__journal_without_eissn__raises_invalid_metadata_error() -> None:
    """Given journal metadata without E-ISSN, raises InvalidMetadataError.

    This documents the current limitation: we require E-ISSN for journal matching.
    When we add ISSN-only support, this test should be updated.
    """
    fake_client, doi = make_test_metadata(
        doi="10.1234/article.456",
        title="Article in Print-Only Journal",
        journal=ExternalJournal(
            title="Print-Only Journal",
            issn="1234-5678",
            eissn=None,
        ),
    )

    doi_service = DOIImportService(doi_client=fake_client)

    with pytest.raises(InvalidMetadataError, match="Journal 'Print-Only Journal' missing E-ISSN"):
        doi_service.import_from_doi(doi)


@pytest.mark.django_db
def test__import_from_doi__metadata_without_publisher__raises_invalid_metadata_error() -> None:
    """Given metadata without publisher information, raises InvalidMetadataError.

    This documents the current limitation: we require publisher for journal creation.
    When we add support for publisher-less journals, this test should be updated.
    """
    fake_client, doi = make_test_metadata(
        doi="10.1234/article.789",
        title="Article Without Publisher Info",
        journal=ExternalJournal(title="Independent Journal", eissn="9876-5434"),
        publisher=None,
    )

    doi_service = DOIImportService(doi_client=fake_client)

    with pytest.raises(InvalidMetadataError, match="Journal missing publisher name"):
        doi_service.import_from_doi(doi)


@pytest.mark.django_db
def test__import_from_doi__invalid_license_string__returns_unknown_license() -> None:
    """Given metadata with invalid/unmappable license string, returns License.Unknown.

    This verifies that we gracefully handle license strings that don't map to CODA's
    License enum by returning License.Unknown instead of raising an exception.
    """
    create_springer_nature_journal()

    fake_client, doi = make_test_metadata(
        doi="10.1234/invalid-license",
        title="Article with Invalid License",
        license="INVALID-LICENSE-XYZ",
        publisher="Springer Nature",
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

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

    fake_client, doi = make_test_metadata(
        doi="10.1234/whitespace-author",
        title="Article with Anonymous Author",
        authors=[
            ExternalAuthor(
                name="   ",
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
def test__import_from_doi__author_with_empty_name_and_ror_id__creates_unknown_author() -> None:
    """Given author with empty name but valid ROR ID, creates 'Unknown' author."""
    create_springer_nature_journal()

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
def test__import_from_doi__author_with_empty_name_and_no_data__skips_author() -> None:
    """Given author with empty name and no other data, skips creating the author entirely."""
    create_springer_nature_journal()

    fake_client, doi = make_test_metadata(
        doi="10.1234/empty-author",
        title="Article with Empty Author",
        authors=[
            ExternalAuthor(
                name="",
                affiliation=None,
                ror_id=None,
            )
        ],
        publisher="Springer Nature",
    )

    doi_service = DOIImportService(doi_client=fake_client)
    funding_request = doi_service.import_from_doi(doi)

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

    # WHEN: Import from DOI
    funding_request = doi_service.import_from_doi(doi)

    # THEN: Publisher was created with trimmed name
    created_publisher = publisher_services.find_by_name("Springer Nature")
    assert created_publisher is not None
    assert created_publisher.name == "Springer Nature"

    # AND: Journal references the trimmed publisher
    publication = get_publication_from_funding_request(funding_request)
    created_journal = journal_services.get_by_pk(publication.journal)
    assert created_journal.publisher.name == "Springer Nature"


@pytest.mark.django_db
def test__import_from_doi__no_publication_date__sets_unpublished_state() -> None:
    """Given metadata without publication date, sets publication state to Unpublished.

    When publication date is missing from DOI metadata:
    - Publication state should be Unpublished (not Published)
    - This allows importing articles that are accepted but not yet published
    """
    create_springer_nature_journal()

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
def test__import_from_doi__only_online_date__sets_published_with_online_date() -> None:
    """Given metadata with only online publication date, sets Published with online date."""
    create_springer_nature_journal()

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
def test__import_from_doi__only_print_date__sets_published_with_print_date() -> None:
    """Given metadata with only print publication date, sets Published with print date."""
    create_springer_nature_journal()

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
def test__import_from_doi__both_dates__sets_published_with_both_dates() -> None:
    """Given metadata with both online and print dates, sets Published with both dates."""
    # GIVEN: Database has existing publisher and journal
    create_springer_nature_journal()

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

    # WHEN: Import from DOI
    funding_request = doi_service.import_from_doi(doi)

    # THEN: Publication state is Published with both dates
    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Published)
    assert publication.publication_state.online == online_date
    assert publication.publication_state.print == print_date


@pytest.mark.django_db
def test__import_from_doi__duplicate_doi__raises_doi_already_imported() -> None:
    """Test that importing a DOI that already exists raises DOIAlreadyImported."""
    # GIVEN: Database has existing publisher, journal, and publication with DOI
    journal_id = create_springer_nature_journal()

    doi = Doi("10.1038/nature12373")

    # Create a publication with this DOI
    publication = domainfactory.publication(JournalId(journal_id))
    publication.links = {doi}
    publication_id = publication_repository.create(publication)

    # Create DOI import service
    fake_client = FakeDOIMetadataClient()
    service = DOIImportService(fake_client)

    # WHEN/THEN: Importing the same DOI raises DOIAlreadyImported
    with pytest.raises(DOIAlreadyImported) as exc_info:
        service.import_from_doi(doi)

    assert exc_info.value.doi == doi
    assert exc_info.value.existing_publication_id == publication_id
