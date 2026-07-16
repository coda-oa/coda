"""DOI Import Service - Creates FundingRequests from DOI metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import TypeAdapter

from coda.contexts.fundingrequest.dto.external_metadata import (
    ExternalFundingMetadata,
    ExternalFundingOrganisationMetadata,
    ExternalPublicationMetadata,
)
from coda.contexts.fundingrequest.dto.preview import (
    PreviewArticle,
    PreviewExternalFunding,
    PreviewFundingRequest,
    PreviewMonograph,
)
from coda.contexts.fundingrequest.services.doi_import.doi_client import DOIMetadataClient
from coda.contexts.fundingrequest.services.doi_import.doi_client._crossref._crossref_type_detector import (
    detect_publication_type,
)
from coda.contexts.fundingrequest.services.doi_import.errors import (
    DOIAlreadyImported,
    InvalidMetadataError,
)
from coda.contexts.fundingrequest.services.funder_resolution import FunderMatch
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.issn import Issn
from coda.domain.publication import JournalId
from coda.domain.publication.links import CrossrefId, Doi, Link
from coda.domain.publication.publication import BasePublication
from coda.domain.string import NonEmptyStr

from ._map_to_preview import build_preview_article, build_preview_monograph

if TYPE_CHECKING:
    from coda.apps.journals.models import Journal
    from coda.apps.publishers.models import Publisher


class DOIRepository(Protocol):
    """Persistence protocol for DOI import operations.

    Abstracts all database operations that ``DOIImportService`` requires,
    allowing both immediate (single-DOI) and unit-of-work (mass-import)
    implementations to share the same interface.
    """

    def find_publication_by_doi(self, doi: Doi) -> BasePublication | None: ...
    def find_journal_by_eissn(self, issn: Issn) -> Journal | None: ...
    def get_journal_by_id(self, journal_id: JournalId) -> Journal: ...
    def create_journal(
        self, title: NonEmptyStr, eissn: Issn, publisher_id: PublisherId
    ) -> JournalId: ...
    def find_publisher_by_name(self, name: str) -> Publisher | None: ...
    def get_publisher_by_id(self, publisher_id: PublisherId) -> Publisher: ...
    def create_publisher(self, name: str) -> PublisherId: ...
    def get_funding_org_names(
        self, ids: list[FundingOrganizationId]
    ) -> dict[FundingOrganizationId, str]: ...
    def create_funding_request(
        self,
        preview: PreviewFundingRequest,
        override: OverrideImport,
        funder_matches: list[FunderMatch],
    ) -> FundingRequestId: ...


@dataclass(frozen=True)
class OverrideFunding:
    funder_id: FundingOrganizationId
    project_id: str


@dataclass(frozen=True)
class OverrideImport:
    _journal_id: JournalId | None = None
    _publisher_id: PublisherId | None = None
    _funding: list[OverrideFunding] | None = None
    _removed_funding: frozenset[tuple[str, str]] = frozenset()

    @classmethod
    def empty(cls) -> OverrideImport:
        return OverrideImport()

    @classmethod
    def as_article(cls, journal_id: JournalId) -> OverrideImport:
        return cls(journal_id)

    @classmethod
    def as_monograph(cls, publisher_id: PublisherId) -> OverrideImport:
        return cls(None, publisher_id)

    def drop_publication_type(self) -> OverrideImport:
        return OverrideImport(_funding=self._funding, _removed_funding=self._removed_funding)

    def into_article(self, journal_id: JournalId) -> OverrideImport:
        return OverrideImport(
            _journal_id=journal_id,
            _publisher_id=None,
            _funding=self._funding,
            _removed_funding=self._removed_funding,
        )

    def into_monograph(self, publisher_id: PublisherId) -> OverrideImport:
        return OverrideImport(
            _journal_id=None,
            _publisher_id=publisher_id,
            _funding=self._funding,
            _removed_funding=self._removed_funding,
        )

    def remove_funding(self, funder: str, project_id: str = "") -> OverrideImport:
        return OverrideImport(
            self._journal_id,
            self._publisher_id,
            self._funding,
            frozenset((*self._removed_funding, *{(funder, project_id)})),
        )

    def add_funding(self, funding: list[OverrideFunding]) -> OverrideImport:
        return OverrideImport(
            self._journal_id,
            self._publisher_id,
            (self._funding or []) + funding,
            self._removed_funding,
        )

    def reset_funding(self) -> OverrideImport:
        return OverrideImport(self._journal_id, self._publisher_id, None, frozenset())

    def overrides_to_article(self) -> bool:
        return self._journal_id is not None

    def overrides_to_monograph(self) -> bool:
        return self._publisher_id is not None

    @property
    def journal_id(self) -> JournalId:
        if self._journal_id is None:
            raise ValueError("OverrideImport does not override to article")
        return self._journal_id

    @property
    def publisher_id(self) -> PublisherId:
        if self._publisher_id is None:
            raise ValueError("OverrideImport does not override to monograph")
        return self._publisher_id

    def apply(
        self, metadata: ExternalPublicationMetadata, repo: DOIRepository
    ) -> ExternalPublicationMetadata:
        keep_funding = [
            funding
            for funding in metadata.funders
            if (funding.funder.name, funding.project_id) not in self._removed_funding
        ]

        name_lookup = self._funding_organizations_to_names(repo)
        added_funding = [
            ExternalFundingMetadata(
                funder=ExternalFundingOrganisationMetadata(name=name_lookup[funding.funder_id]),
                project_id=funding.project_id,
            )
            for funding in self._funding or []
            if (name_lookup[funding.funder_id], funding.project_id) not in self._removed_funding
        ]

        metadata = metadata.override_funding(keep_funding + added_funding)

        if self._journal_id:
            journal = repo.get_journal_by_id(self._journal_id)
            return metadata.override_journal(journal)
        elif self._publisher_id:
            publisher = repo.get_publisher_by_id(self._publisher_id)
            return metadata.override_publisher(publisher)

        return metadata

    def _funding_organizations_to_names(
        self, repo: DOIRepository
    ) -> dict[FundingOrganizationId, str]:
        return repo.get_funding_org_names([funding.funder_id for funding in self._funding or []])


OverrideImportTypeAdapter = TypeAdapter(OverrideImport)


def _default_repo() -> DOIRepository:
    from coda.contexts.fundingrequest.services.doi_import._repository_immediate import (
        ImmediateDOIRepository,
    )

    return ImmediateDOIRepository()


class DOIImportService:
    """Import publication metadata from DOI and create a FundingRequest.

    The service uses an optional metadata cache to avoid re-fetching from external APIs.
    """

    def __init__(
        self,
        doi_client: DOIMetadataClient,
        repo: DOIRepository | None = None,
        metadata_cache: dict[Doi, ExternalPublicationMetadata] | None = None,
    ) -> None:
        """Initialize the service with a DOI client.

        Args:
            doi_client: Client to fetch metadata from external APIs (e.g., Crossref)
            repo: Repository for database operations. Defaults to ``ImmediateDOIRepository``.
            metadata_cache: Optional pre-populated cache of raw metadata (avoids re-fetching)
        """
        self.doi_client = doi_client
        self._repo = repo or _default_repo()
        self.metadata_cache: dict[Doi, ExternalPublicationMetadata] = metadata_cache or {}

    def _fetch_metadata(self, doi: Doi) -> ExternalPublicationMetadata:
        """Fetch metadata from cache or external API."""
        if doi not in self.metadata_cache:
            self.metadata_cache[doi] = self.doi_client.fetch_publication(doi)
        return self.metadata_cache[doi]

    def _fetch_preview_from_metadata(
        self, doi: Doi, metadata: ExternalPublicationMetadata
    ) -> PreviewArticle | PreviewMonograph:
        detected_type = detect_publication_type(metadata)
        publication_preview: PreviewArticle | PreviewMonograph
        match detected_type:
            case "article":
                publication_preview = build_preview_article(doi, metadata)
            case "monograph":
                publication_preview = build_preview_monograph(doi, metadata)

        return publication_preview

    def fetch_doi_preview(self, doi: Doi) -> PreviewFundingRequest:
        """Build a preview FundingRequest DTO without creating database entities.

        This method does NOT check if the DOI already exists and does NOT create
        journals, publishers, or funding requests. Use this for preview workflows
        where you want to show the user what will be imported before persisting.

        Args:
            doi: The DOI to import

        Returns:
            PreviewFundingRequest with publication metadata (no database IDs)

        Raises:
            DOINotFoundError: If DOI not found (when fetching)
            DOIFetchError: If fetch fails (when fetching)
            InvalidMetadataError: If metadata is invalid
        """
        publication_preview = self._fetch_preview_from_metadata(doi, self._fetch_metadata(doi))
        return PreviewFundingRequest(publication=publication_preview)

    def preview_with_override(
        self,
        doi: Doi,
        override: OverrideImport = OverrideImport.empty(),
    ) -> PreviewFundingRequest:
        """Build a preview with an explicit publication type override.

        Fetches metadata from cache (no Crossref re-fetch), resolves the selected
        journal or publisher by DB ID, and builds the appropriate preview DTO.
        """
        publication: PreviewArticle | PreviewMonograph
        metadata = override.apply(self._fetch_metadata(doi), self._repo)
        if override.overrides_to_article():
            publication = build_preview_article(doi, metadata)
            return PreviewFundingRequest(publication=publication)
        elif override.overrides_to_monograph():
            publication = build_preview_monograph(doi, metadata)
            return PreviewFundingRequest(publication=publication)

        publication = self._fetch_preview_from_metadata(doi, metadata)
        return PreviewFundingRequest(publication=publication)

    def import_from_doi(
        self, doi: Doi, override: OverrideImport = OverrideImport.empty()
    ) -> FundingRequestId:
        """Fetch metadata from DOI and create a FundingRequest in the database.

        Delegates DTO building and persistence to the injected ``DOIRepository``
        so the caller controls the timing of database operations.

        Returns:
            The ID of the created funding request

        Raises:
            DOIAlreadyImported: If DOI already exists
            DOINotFoundError: If DOI not found
            DOIFetchError: If fetch fails
            InvalidMetadataError: If metadata is invalid
        """
        self._ensure_doi_not_already_imported(doi)
        preview = self.preview_with_override(doi, override)
        self._validate_preview(preview)
        funder_matches = self._build_funder_matches(preview.publication.funding)
        return self._repo.create_funding_request(preview, override, funder_matches)

    def _ensure_doi_not_already_imported(self, doi: Doi) -> None:
        """Verify DOI has not been imported previously."""

        existing_publication = self._repo.find_publication_by_doi(doi)
        if not existing_publication:
            return

        if existing_publication.id is None:
            raise InvalidMetadataError("Publication from database missing ID")

        raise DOIAlreadyImported(
            doi,
            existing_publication.id,
            existing_publication.title,
            existing_publication.relevant_authors,
        )

    def _validate_preview(self, preview: PreviewFundingRequest) -> None:
        """Validate the preview has the required metadata for its publication type.

        Raises ``InvalidMetadataError`` immediately (per-DOI) rather than
        letting the error surface later at commit time where it would kill
        every DOI in a batch instead of just the one with bad metadata.

        Raises:
            InvalidMetadataError: If a journal article lacks journal metadata
                or a monograph lacks a publisher name.
        """
        match preview.publication:
            case PreviewArticle() as article:
                if article.journal is None:
                    raise InvalidMetadataError("Journal article missing journal metadata")
                if article.journal.eissn is None:
                    raise InvalidMetadataError(f"Journal '{article.journal.title}' missing E-ISSN")
            case PreviewMonograph() as monograph:
                if monograph.publisher_name is None:
                    raise InvalidMetadataError("Monograph missing publisher name")

    def _build_funder_matches(self, funding: list[PreviewExternalFunding]) -> list[FunderMatch]:
        """Turn preview funders into domain ``FunderMatch`` objects.

        Parses each funder's raw identifier strings into validated domain
        ``Link`` objects via ``_funder_links``. ROR enrichment happens later,
        inside ``resolve_funders`` (owned by the fundingrequest context).
        """
        return [
            FunderMatch(name=f.name, links=tuple(_funder_links(f.identifiers))) for f in funding
        ]


def _funder_links(identifiers: list[str]) -> list[Link]:
    """Turn raw metadata identifier strings into validated domain ``Link`` objects.

    A valid DOI becomes a ``Doi``; a pure-digit Crossref ID becomes a
    ``CrossrefId``. Invalid identifiers surface as domain errors rather than
    being silently dropped.

    Crossref funder IDs live under the ``10.13039`` DOI prefix, so a ``Doi`` of
    that form (e.g. ``10.13039/501100008530``) is normalized to its bare
    ``CrossrefId`` (``501100008530``). This collapses the prefixed and bare forms
    of the same funder ID into a single link instead of storing both.
    """
    links: list[Link] = []
    for id_ in identifiers:
        try:
            links.append(Doi(id_))
        except ValueError:
            if id_.isdigit():
                links.append(CrossrefId(id_))
    return links
