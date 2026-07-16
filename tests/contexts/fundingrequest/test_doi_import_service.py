"""Tests for DOI Import Service (Outside-In).

These tests verify the complete flow from DOI → FundingRequest with pre-populated Publication.
Tests are parametrized to run with both fake and real Crossref clients.
"""

import datetime

import pytest
from tests import domainfactory
from tests.contexts.fundingrequest.fixtures import (
    NATURE_EISSN,
    NATURE_JOURNAL_TITLE,
    NatureArticleScenario,
    SpringerBookScenario,
)
from tests.contexts.fundingrequest.fixtures.sample_metadata import (
    SPRINGER_NATURE_PUBLISHER,
    ArticleScenario,
    BookScenario,
)
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq
from tests.test_orcid import JOSIAH_CARBERRY

from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.journals import services as journal_services
from coda.apps.journals.models import Journal
from coda.apps.publications.repositories import publication_repository
from coda.apps.publishers import services as publisher_services
from coda.apps.publishers.models import Publisher
from coda.contexts.fundingrequest.dto.preview import PreviewArticle, PreviewMonograph
from coda.contexts.fundingrequest.services.doi_import.doi_client import (
    InMemoryDOIMetadataClient,
    crossref,
)
from coda.contexts.fundingrequest.services.doi_import._service import (
    DOIImportService,
    OverrideImport,
)
from coda.contexts.fundingrequest.services.doi_import.errors import (
    DOIAlreadyImported,
    InvalidMetadataError,
)
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.issn import Issn
from coda.domain.publication import (
    JournalId,
    License,
    Publication,
    Published,
    Unpublished,
    UnpublishedState,
)
from coda.domain.publication.links import Doi
from coda.domain.string import NonEmptyStr


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


@pytest.fixture(
    params=[
        "fake",
        pytest.param("real", marks=[pytest.mark.integration]),
    ]
)
def nature_scenario(request: pytest.FixtureRequest) -> NatureArticleScenario:
    if request.param == "fake":
        return NatureArticleScenario.with_in_memory_client()
    return NatureArticleScenario(crossref)


@pytest.fixture(
    params=[
        "fake",
        pytest.param("real", marks=[pytest.mark.integration]),
    ]
)
def springer_scenario(request: pytest.FixtureRequest) -> SpringerBookScenario:
    if request.param == "fake":
        return SpringerBookScenario.with_in_memory_client()
    return SpringerBookScenario(crossref)


@pytest.mark.django_db
def test__import_from_doi__article_without_journal__raises_invalid_metadata_error() -> None:
    """Article metadata missing journal info should raise InvalidMetadataError per-DOI during import.

    Without this check the error surfaces only at commit time, killing all DOIs
    in a batch instead of just the one with incomplete metadata.
    """
    from coda.contexts.fundingrequest.dto.external_metadata import (
        ExternalAuthor,
        ExternalPublicationMetadata,
    )
    from coda.contexts.fundingrequest.services.doi_import.doi_client._inmemory import (
        InMemoryDOIMetadataClient,
    )
    from coda.contexts.fundingrequest.services.doi_import._service import DOIImportService
    from coda.contexts.fundingrequest.services.doi_import._repository_uow import (
        UnitOfWorkDOIRepository,
    )
    from coda.contexts.fundingrequest.services.doi_import.errors import InvalidMetadataError
    from coda.domain.publication.links import Doi

    doi = Doi("10.1234/test-no-journal")
    metadata = ExternalPublicationMetadata(
        title="Test Article Without Journal",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="journal-article",
        journal=None,
        publisher="Test Publisher",
    )
    client = InMemoryDOIMetadataClient()
    client.data[str(doi)] = metadata

    repo = UnitOfWorkDOIRepository()
    sut = DOIImportService(doi_client=client, repo=repo)

    with pytest.raises(InvalidMetadataError, match="missing journal metadata"):
        sut.import_from_doi(doi)


@pytest.mark.django_db
def test__import_from_doi__article_with_journal_without_eissn__raises_invalid_metadata_error() -> (
    None
):
    """Article with a journal object but no E-ISSN should raise InvalidMetadataError per-DOI.

    Without this check the error surfaces only at commit time as
    'Journal \'...\' missing E-ISSN', killing all DOIs in a batch.
    """
    from coda.contexts.fundingrequest.dto.external_metadata import (
        ExternalAuthor,
        ExternalJournal,
        ExternalPublicationMetadata,
    )
    from coda.contexts.fundingrequest.services.doi_import.doi_client._inmemory import (
        InMemoryDOIMetadataClient,
    )
    from coda.contexts.fundingrequest.services.doi_import._service import DOIImportService
    from coda.contexts.fundingrequest.services.doi_import._repository_uow import (
        UnitOfWorkDOIRepository,
    )
    from coda.contexts.fundingrequest.services.doi_import.errors import InvalidMetadataError
    from coda.domain.publication.links import Doi

    doi = Doi("10.1234/test-no-eissn")
    metadata = ExternalPublicationMetadata(
        title="Test Article Without E-ISSN",
        authors=[ExternalAuthor(name="Test Author")],
        publication_type="journal-article",
        journal=ExternalJournal(title="Molecular Genetics and Metabolism", eissn=None),
        publisher="Test Publisher",
    )
    client = InMemoryDOIMetadataClient()
    client.data[str(doi)] = metadata

    repo = UnitOfWorkDOIRepository()
    sut = DOIImportService(doi_client=client, repo=repo)

    with pytest.raises(InvalidMetadataError, match="missing E-ISSN"):
        sut.import_from_doi(doi)


@pytest.mark.django_db
def test__import_from_doi__valid_journal_article_doi__returns_funding_request_with_populated_publication(
    nature_scenario: NatureArticleScenario,
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
    nature_scenario.setup_db()
    sut = DOIImportService(doi_client=nature_scenario.client)

    funding_request_id = sut.import_from_doi(nature_scenario.doi)

    actual = fundingrequest_repository.get_by_id(funding_request_id)
    expected = nature_scenario.get_expected_fundingrequest()
    assert_fundingrequest_eq(actual, expected)


@pytest.mark.django_db
def test__import_from_doi__valid_book_doi__returns_funding_request_with_populated_monograph(
    springer_scenario: SpringerBookScenario,
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
    springer_scenario.setup_db()
    sut = DOIImportService(doi_client=springer_scenario.client)

    funding_request_id = sut.import_from_doi(springer_scenario.doi)

    actual = fundingrequest_repository.get_by_id(funding_request_id)
    expected = springer_scenario.get_expected_fundingrequest()
    assert_fundingrequest_eq(actual, expected)


@pytest.mark.django_db
def test__import_from_doi__journal_not_in_database__auto_creates_journal(
    nature_scenario: NatureArticleScenario,
) -> None:
    """Given a DOI with E-ISSN not in database, automatically creates the journal.

    The new journal should be created with:
    - Title from DOI metadata
    - E-ISSN from DOI metadata
    - Publisher matched by name (or created if not found)
    """
    sut = DOIImportService(doi_client=nature_scenario.client)

    sut.import_from_doi(nature_scenario.doi)

    created_journal = journal_services.find_by_eissn(Issn(NATURE_EISSN))
    assert created_journal is not None
    assert created_journal.title == NATURE_JOURNAL_TITLE
    assert created_journal.eissn == NATURE_EISSN

    assert created_journal.publisher is not None
    assert created_journal.publisher.name == SPRINGER_NATURE_PUBLISHER


@pytest.mark.django_db
def test__import_from_doi__journal_exists_in_database__does_not_create_publisher(
    nature_scenario: NatureArticleScenario,
) -> None:
    """Given a DOI with E-ISSN that exists in database, does NOT create a new publisher.

    This verifies that when the journal already exists, we:
    - Use the existing journal (with its existing publisher)
    - Do NOT create any new publishers
    """
    publisher_id = publisher_services.create(SPRINGER_NATURE_PUBLISHER)
    journal_id = journal_services.create(
        title=NonEmptyStr(NATURE_JOURNAL_TITLE),
        eissn=Issn(NATURE_EISSN),
        publisher_id=publisher_id,
    )
    sut = DOIImportService(doi_client=nature_scenario.client)

    funding_request_id = sut.import_from_doi(nature_scenario.doi)

    assert Journal.objects.count() == 1
    assert Publisher.objects.count() == 1
    funding_request = fundingrequest_repository.get_by_id(funding_request_id)
    publication = funding_request.publication
    assert isinstance(publication, Publication)
    assert publication.journal == int(journal_id)


@pytest.mark.django_db
def test__import_from_doi__monograph_without_publisher__raises_invalid_metadata_error() -> None:
    """Given book/monograph metadata without publisher, raises InvalidMetadataError.

    Monographs are now supported, but require a publisher name.
    """
    scenario = BookScenario().without_publisher().setup_client()

    sut = DOIImportService(doi_client=scenario.client)

    with pytest.raises(InvalidMetadataError, match="Monograph missing publisher name"):
        sut.import_from_doi(scenario.doi)


@pytest.mark.django_db
def test__import_from_doi__journal_without_eissn__raises_invalid_metadata_error() -> None:
    """Given journal metadata without E-ISSN, raises InvalidMetadataError.

    This documents the current limitation: we require E-ISSN for journal matching.
    When we add ISSN-only support, this test should be updated.
    """
    scenario = ArticleScenario().with_journal(eissn=None).setup_client()

    sut = DOIImportService(doi_client=scenario.client)

    with pytest.raises(InvalidMetadataError):
        sut.import_from_doi(scenario.doi)


@pytest.mark.django_db
def test__import_from_doi__metadata_without_publisher__raises_invalid_metadata_error() -> None:
    """Given metadata without publisher information, raises InvalidMetadataError.

    This documents the current limitation: we require publisher for journal creation.
    When we add support for publisher-less journals, this test should be updated.
    """

    scenario = ArticleScenario().without_publisher().setup_client()

    sut = DOIImportService(doi_client=scenario.client)

    with pytest.raises(InvalidMetadataError, match="Journal missing publisher name"):
        sut.import_from_doi(scenario.doi)


@pytest.mark.django_db
def test__import_from_doi__invalid_license_string__returns_unknown_license() -> None:
    """Given metadata with invalid/unmappable license string, returns License.Unknown.

    This verifies that we gracefully handle license strings that don't map to CODA's
    License enum by returning License.Unknown instead of raising an exception.
    """
    scenario = ArticleScenario().with_invalid_license().setup_client()

    sut = DOIImportService(doi_client=scenario.client)
    funding_request = sut.import_from_doi(scenario.doi)

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
    scenario = (
        ArticleScenario()
        .with_authors((" ", "Massachusetts Institute of Technology", None))
        .setup_client()
    )

    sut = DOIImportService(doi_client=scenario.client)
    funding_request = sut.import_from_doi(scenario.doi)

    publication = get_publication_from_funding_request(funding_request)
    assert len(publication.relevant_authors) == 1
    assert publication.relevant_authors[0].name == "Unknown"


@pytest.mark.django_db
def test__import_from_doi__author_with_empty_name_and_ror_id__creates_unknown_author() -> None:
    """Given author with empty name but valid ROR ID, creates 'Unknown' author."""
    scenario = ArticleScenario().with_authors(("", None, JOSIAH_CARBERRY)).setup_client()

    sut = DOIImportService(doi_client=scenario.client)
    funding_request = sut.import_from_doi(scenario.doi)

    publication = get_publication_from_funding_request(funding_request)
    assert len(publication.relevant_authors) == 1
    assert publication.relevant_authors[0].name == "Unknown"


@pytest.mark.django_db
def test__import_from_doi__author_with_empty_name_and_no_data__skips_author() -> None:
    """Given author with empty name and no other data, skips creating the author entirely."""
    scenario = ArticleScenario().with_authors(("", None, None)).setup_client()

    sut = DOIImportService(doi_client=scenario.client)
    funding_request = sut.import_from_doi(scenario.doi)

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

    author_with_valid_name = ("John Doe", "MIT", None)
    author_with_whitespace_name_but_affiliation = ("  ", "Harvard", None)
    author_with_no_name_and_no_data = ("", None, None)
    another_author_with_valid_name = ("Jane Smith", None, None)
    scenario = (
        ArticleScenario()
        .with_authors(
            author_with_valid_name,
            author_with_whitespace_name_but_affiliation,
            author_with_no_name_and_no_data,
            another_author_with_valid_name,
        )
        .setup_client()
    )

    sut = DOIImportService(doi_client=scenario.client)

    funding_request = sut.import_from_doi(scenario.doi)

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
    scenario = ArticleScenario().with_publisher(publisher_with_whitespace).setup_client()
    sut = DOIImportService(doi_client=scenario.client)

    funding_request = sut.import_from_doi(scenario.doi)

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
    scenario = ArticleScenario().without_online_date().without_print_date().setup_client()

    sut = DOIImportService(doi_client=scenario.client)
    funding_request = sut.import_from_doi(scenario.doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Unpublished)
    assert publication.publication_state.state == UnpublishedState.Unknown


@pytest.mark.django_db
def test__import_from_doi__only_online_date__sets_published_with_online_date() -> None:
    """Given metadata with only online publication date, sets Published with online date."""
    online_date = datetime.date(2024, 6, 15)
    scenario = ArticleScenario().with_online_date(online_date).without_print_date().setup_client()
    sut = DOIImportService(doi_client=scenario.client)

    funding_request = sut.import_from_doi(scenario.doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Published)
    assert publication.publication_state.online == online_date
    assert publication.publication_state.print is None


@pytest.mark.django_db
def test__import_from_doi__only_print_date__sets_published_with_print_date() -> None:
    """Given metadata with only print publication date, sets Published with print date."""
    print_date = datetime.date(2024, 7, 1)
    scenario = ArticleScenario().without_online_date().with_print_date(print_date).setup_db()

    sut = DOIImportService(doi_client=scenario.client)
    funding_request = sut.import_from_doi(scenario.doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Published)
    assert publication.publication_state.online is None
    assert publication.publication_state.print == print_date


@pytest.mark.django_db
def test__import_from_doi__both_dates__sets_published_with_both_dates() -> None:
    """Given metadata with both online and print dates, sets Published with both dates."""
    online_date = datetime.date(2024, 5, 1)
    print_date = datetime.date(2024, 6, 1)
    scenario = (
        ArticleScenario().with_online_date(online_date).with_print_date(print_date).setup_db()
    )
    sut = DOIImportService(doi_client=scenario.client)

    funding_request = sut.import_from_doi(scenario.doi)

    publication = get_publication_from_funding_request(funding_request)
    assert isinstance(publication.publication_state, Published)
    assert publication.publication_state.online == online_date
    assert publication.publication_state.print == print_date


@pytest.mark.django_db
def test__import_from_doi__duplicate_doi__raises_doi_already_imported() -> None:
    """Test that importing a DOI that already exists raises DOIAlreadyImported."""
    scenario = NatureArticleScenario.with_in_memory_client().setup_db()
    doi = Doi("10.1038/nature12373")

    publication = domainfactory.publication(JournalId(scenario.journal_id))
    publication.links = {doi}
    publication_id = publication_repository.create(publication)

    fake_client = InMemoryDOIMetadataClient()
    sut = DOIImportService(fake_client)

    with pytest.raises(DOIAlreadyImported) as exc_info:
        sut.import_from_doi(doi)

    assert exc_info.value.doi == doi
    assert exc_info.value.publication_id == publication_id


@pytest.mark.django_db
def test__fetch_doi_preview__returns_dto_without_persisting() -> None:
    """Test that fetch_doi_preview returns DTO without creating database records."""
    scenario = NatureArticleScenario.with_in_memory_client()
    scenario.setup_db()

    sut = DOIImportService(scenario.client)
    sut.fetch_doi_preview(scenario.doi)

    all_requests = fundingrequest_repository.all()
    assert len(all_requests) == 0


@pytest.mark.django_db
def test__fetch_doi_preview__article__does_not_create_journal_or_publisher() -> None:
    """Test that fetch_doi_preview does NOT create journals or publishers for articles.

    This is critical for preview workflows - we should only build the DTO without
    persisting any entities. Journal/publisher creation should happen during import_from_doi().
    """
    # Arrange - Verify database starts empty (no journals or publishers)
    scenario = ArticleScenario().setup_client()

    sut = DOIImportService(scenario.client)

    # Act
    dto = sut.fetch_doi_preview(scenario.doi)

    # Assert - DTO should be created successfully
    assert dto is not None
    assert isinstance(dto.publication, PreviewArticle)

    # Assert - No database entities should be created
    assert Journal.objects.count() == 0, "fetch_doi_preview created a journal"
    assert Publisher.objects.count() == 0, "fetch_doi_preview created a publisher"
    assert len(fundingrequest_repository.all()) == 0, "fetch_doi_preview created a funding request"


@pytest.mark.django_db
def test__fetch_doi_preview__monograph__does_not_create_publisher() -> None:
    """Test that fetch_doi_preview does NOT create publishers for monographs.

    This is critical for preview workflows - we should only build the DTO without
    persisting any entities. Publisher creation should happen during import_from_doi().
    """
    scenario = BookScenario().setup_client()
    sut = DOIImportService(scenario.client)

    # Act
    dto = sut.fetch_doi_preview(scenario.doi)

    # Assert - DTO should be created successfully
    assert dto is not None
    assert isinstance(dto.publication, PreviewMonograph)

    # Assert - No database entities should be created
    assert Publisher.objects.count() == 0, "fetch_doi_preview created a publisher"
    assert len(fundingrequest_repository.all()) == 0, "fetch_doi_preview created a funding request"


@pytest.mark.django_db
def test__build_preview_with_type_override__to_article__uses_resolved_journal() -> None:
    """Overriding to article uses journal title and EISSN from the resolved DB journal."""
    scenario = ArticleScenario().setup_client()
    publisher_id = publisher_services.create(name="Test Publisher")
    journal_id = journal_services.create(
        title=NonEmptyStr(NATURE_JOURNAL_TITLE),
        eissn=Issn(NATURE_EISSN),
        publisher_id=publisher_id,
    )

    service = DOIImportService(doi_client=scenario.client)
    result = service.preview_with_override(scenario.doi, OverrideImport.as_article(journal_id))

    assert isinstance(result.publication, PreviewArticle)
    assert result.publication.journal is not None
    assert result.publication.journal.title == NATURE_JOURNAL_TITLE
    assert result.publication.journal.eissn == NATURE_EISSN


@pytest.mark.django_db
def test__build_preview_with_type_override__to_monograph__uses_resolved_publisher() -> None:
    """Overriding to monograph uses publisher name from the resolved DB publisher."""
    scenario = ArticleScenario().setup_client()
    publisher_id = publisher_services.create(name="Springer Nature")

    service = DOIImportService(doi_client=scenario.client)
    result = service.preview_with_override(scenario.doi, OverrideImport.as_monograph(publisher_id))

    assert isinstance(result.publication, PreviewMonograph)
    assert result.publication.publisher_name == "Springer Nature"
