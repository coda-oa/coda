import pytest

from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.contexts.publication.services.doi_client import InMemoryDOIMetadataClient
from coda.contexts.publication.services.doi_import_service import DOIImportService, OverrideImport
from coda.contexts.publication.services.mass_doi_import_service import MassDOIImportService
from coda.domain.publication.links import Doi

from tests.contexts.publication.fixtures.sample_metadata import ArticleScenario, BookScenario
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq


class TestFetchMulti:
    """Tests for MassDOIImportService.fetch_multi() — batch fetching."""

    def test__fetch_multi__single_valid_article_doi__returns_single_preview(self) -> None:
        """Given a single valid article DOI, returns one success and no errors."""
        scenario = ArticleScenario(doi="10.1234/test.fetch.article")
        scenario.setup_client()

        sut = MassDOIImportService(doi_client=scenario.client)
        preview = sut.fetch_multi([scenario.doi])

        assert len(preview.successes) == 1
        assert len(preview.errors) == 0
        assert preview.successes[0].doi == scenario.doi
        assert preview.successes[0].publication_type == "article"

    def test__fetch_multi__single_valid_book_doi__returns_monograph_preview(self) -> None:
        """Given a single valid book DOI, returns one success with monograph type."""
        scenario = BookScenario(doi="10.1234/test.fetch.book")
        scenario.setup_client()

        sut = MassDOIImportService(doi_client=scenario.client)
        preview = sut.fetch_multi([scenario.doi])

        assert len(preview.successes) == 1
        assert len(preview.errors) == 0
        assert preview.successes[0].publication_type == "monograph"

    def test__fetch_multi__two_valid_dois__returns_two_previews(self) -> None:
        """Given two valid DOIs (article + book), returns two successes."""
        client = InMemoryDOIMetadataClient()
        article = ArticleScenario(client=client, doi="10.1234/test.article").setup_client()
        book = BookScenario(client=client, doi="10.1234/test.book").setup_client()

        sut = MassDOIImportService(doi_client=client)
        preview = sut.fetch_multi([article.doi, book.doi])

        assert len(preview.successes) == 2
        assert len(preview.errors) == 0

    def test__fetch_multi__mixed_found_and_not_found__returns_mixed_results(self) -> None:
        """Given a mix of found and not-found DOIs, returns successes and errors."""
        client = InMemoryDOIMetadataClient()
        found = ArticleScenario(client=client, doi="10.1234/test.found").setup_client()

        not_found_doi = Doi("10.1234/test.notfound")
        sut = MassDOIImportService(doi_client=client)
        preview = sut.fetch_multi([found.doi, not_found_doi])

        assert len(preview.successes) == 1
        assert len(preview.errors) == 1
        assert preview.successes[0].doi == found.doi
        assert preview.errors[0].doi == not_found_doi

    def test__fetch_multi__all_not_found__returns_all_errors(self) -> None:
        """Given DOIs that don't exist, returns all errors."""
        client = InMemoryDOIMetadataClient()
        doi_a = Doi("10.1234/test.missing.a")
        doi_b = Doi("10.1234/test.missing.b")

        sut = MassDOIImportService(doi_client=client)
        preview = sut.fetch_multi([doi_a, doi_b])

        assert len(preview.successes) == 0
        assert len(preview.errors) == 2
        assert preview.errors[0].doi in (doi_a, doi_b)
        assert preview.errors[1].doi in (doi_a, doi_b)

    def test__fetch_multi__empty_doi_list__returns_empty_preview(self) -> None:
        """Given an empty list of DOIs, returns empty preview."""
        client = InMemoryDOIMetadataClient()

        sut = MassDOIImportService(doi_client=client)
        preview = sut.fetch_multi([])

        assert len(preview.successes) == 0
        assert len(preview.errors) == 0


class TestImportMulti:
    """Tests for MassDOIImportService.import_multi() — batch importing."""

    @pytest.mark.django_db
    def test__import_multi__single_article__creates_correct_funding_request(self) -> None:
        """Given a single article DOI, creates a funding request matching expected state."""
        client = InMemoryDOIMetadataClient()
        scenario = ArticleScenario(client=client, doi="10.1234/test.import.article").setup_db()

        sut = MassDOIImportService(doi_client=client)
        result = sut.import_multi(
            [(scenario.doi, OverrideImport.empty())],
            metadata_cache={},
        )

        assert len(result.imported) == 1
        assert len(result.skipped) == 0
        assert len(result.failed) == 0

        doi, fr_id = result.imported[0]
        assert doi == scenario.doi
        actual = fundingrequest_repository.get_by_id(fr_id)
        assert_fundingrequest_eq(actual, scenario.get_expected_fundingrequest())

    @pytest.mark.django_db
    def test__import_multi__article_and_book__creates_both_correctly(self) -> None:
        """Given an article and a book DOI, creates both with correct structure."""
        client = InMemoryDOIMetadataClient()
        article = ArticleScenario(client=client, doi="10.1234/test.multi.article").setup_db()
        book = BookScenario(client=client, doi="10.1234/test.multi.book").setup_db()

        sut = MassDOIImportService(doi_client=client)
        result = sut.import_multi(
            [
                (article.doi, OverrideImport.empty()),
                (book.doi, OverrideImport.empty()),
            ],
            metadata_cache={},
        )

        assert len(result.imported) == 2
        assert len(result.skipped) == 0
        assert len(result.failed) == 0

        _, article_id = result.imported[0]
        _, book_id = result.imported[1]
        actual = fundingrequest_repository.get_by_id(article_id)
        assert_fundingrequest_eq(actual, article.get_expected_fundingrequest())

        actual = fundingrequest_repository.get_by_id(book_id)
        assert_fundingrequest_eq(actual, book.get_expected_fundingrequest())

    @pytest.mark.django_db
    def test__import_multi__one_doi_already_imported__skips_duplicate(self) -> None:
        """Given a DOI that was previously imported, skips it.

        The first import creates a real FundingRequest via the standard import
        pathway (DOIImportService.import_from_doi). The second attempt via
        batch import should detect the existing Publication and skip.
        """
        client = InMemoryDOIMetadataClient()
        article = ArticleScenario(client=client, doi="10.1234/test.dedup").setup_db()
        single_service = DOIImportService(doi_client=client)
        single_service.import_from_doi(article.doi)

        sut = MassDOIImportService(doi_client=client)
        result = sut.import_multi([(article.doi, OverrideImport.empty())], {})

        assert len(result.imported) == 0
        assert len(result.skipped) == 1
        assert len(result.failed) == 0
        assert result.skipped[0][0] == article.doi
