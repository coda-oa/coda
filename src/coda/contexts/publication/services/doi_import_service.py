"""DOI Import Service - Creates FundingRequests from DOI metadata."""

from __future__ import annotations

from dataclasses import dataclass

from coda.apps.fundingrequests import repository
from coda.apps.journals import services as journal_services
from coda.apps.publications.dto import MonographDto, PublicationDto
from coda.apps.publications.repositories import publication_repository
from coda.apps.publishers import services as publisher_services
from coda.contexts.fundingrequest.dto.commands import (
    CreateFundingRequestDto,
    ExternalFundingDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.contexts.fundingrequest.services import fundingrequests
from coda.contexts.fundingrequest.services.funder_resolver import (
    FunderMatch,
    resolve_funders,
)
from coda.contexts.publication.dto.external_metadata import (
    ExternalFundingMetadata,
    ExternalFundingOrganisationMetadata,
    ExternalPublicationMetadata,
)
from coda.contexts.publication.dto.preview import (
    PreviewArticle,
    PreviewExternalFunding,
    PreviewFundingRequest,
    PreviewMonograph,
)
from coda.contexts.publication.services.doi_client import DOIMetadataClient
from coda.contexts.publication.services.doi_client._crossref._crossref_type_detector import (
    detect_publication_type,
)
from coda.contexts.publication.services.errors import DOIAlreadyImported, InvalidMetadataError
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.issn import Issn
from coda.domain.publication import JournalId
from coda.domain.publication.links import Doi
from coda.domain.string import NonEmptyStr
from pydantic import TypeAdapter

from ._map_to_preview import build_preview_article, build_preview_monograph


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

    def apply(self, metadata: ExternalPublicationMetadata) -> ExternalPublicationMetadata:
        keep_funding = [
            funding
            for funding in metadata.funders
            if (funding.funder.name, funding.project_id) not in self._removed_funding
        ]

        name_lookup = self._funding_organizations_to_names()
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
            journal = journal_services.get_by_pk(self._journal_id)
            return metadata.override_journal(journal)
        elif self._publisher_id:
            publisher = publisher_services.get_by_pk(self._publisher_id)
            return metadata.override_publisher(publisher)

        return metadata

    def _funding_organizations_to_names(self) -> dict[FundingOrganizationId, str]:
        organizations = repository.get_funding_organizations_by_ids(
            [funding.funder_id for funding in self._funding or []]
        )
        return {FundingOrganizationId(org.pk): org.name for org in organizations}


OverrideImportTypeAdapter = TypeAdapter(OverrideImport)


class DOIImportService:
    """Import publication metadata from DOI and create a FundingRequest.

    The service uses an optional metadata cache to avoid re-fetching from external APIs.
    """

    def __init__(
        self,
        doi_client: DOIMetadataClient,
        metadata_cache: dict[Doi, ExternalPublicationMetadata] | None = None,
    ) -> None:
        """Initialize the service with a DOI client and optional metadata cache.

        Args:
            doi_client: Client to fetch metadata from external APIs (e.g., Crossref)
            metadata_cache: Optional pre-populated cache of raw metadata (avoids re-fetching)
        """
        self.doi_client = doi_client
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
        metadata = override.apply(self._fetch_metadata(doi))
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

        Returns:
            The ID of the created funding request

        Raises:
            DOIAlreadyImported: If DOI already exists
            DOINotFoundError: If DOI not found
            DOIFetchError: If fetch fails
            InvalidMetadataError: If metadata is invalid
        """
        self._ensure_doi_not_already_imported(doi)
        preview_dto = self.preview_with_override(doi, override)
        creation_dto = self._convert_preview_to_creation_dto(preview_dto, override)
        return fundingrequests.create_fundingrequest(creation_dto)

    def _ensure_doi_not_already_imported(self, doi: Doi) -> None:
        """Verify DOI has not been imported previously."""

        existing_publication = publication_repository.find_by_doi(doi)
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

    def _match_or_create_journal(self, issn: Issn, publication: PreviewArticle) -> JournalId:
        journal = journal_services.find_by_eissn(issn)
        if journal:
            return JournalId(journal.pk)

        if publication.journal is None:
            raise InvalidMetadataError("Journal article missing journal metadata")

        if not publication.journal.title:
            raise InvalidMetadataError("Journal missing title")

        if publication.publisher_name is None:
            raise InvalidMetadataError("Journal missing publisher name")

        publisher_id = self._match_or_create_publisher(publication.publisher_name)
        return journal_services.create(
            title=NonEmptyStr(publication.journal.title), eissn=issn, publisher_id=publisher_id
        )

    def _resolve_article_dto(self, publication: PreviewArticle) -> PublicationDto:
        """Resolve journal entity and convert article preview to creation DTO.

        Raises:
            InvalidMetadataError: If journal metadata or E-ISSN is missing
        """
        if publication.journal is None:
            raise InvalidMetadataError("Journal article missing journal metadata")
        if publication.journal.eissn is None:
            raise InvalidMetadataError(f"Journal '{publication.journal.title}' missing E-ISSN")
        issn = Issn(publication.journal.eissn)
        journal_id = self._match_or_create_journal(issn, publication)
        return publication.to_publication_dto(journal_id=journal_id)

    def _resolve_monograph_dto(self, publication: PreviewMonograph) -> MonographDto:
        """Resolve publisher entity and convert monograph preview to creation DTO.

        Raises:
            InvalidMetadataError: If publisher name is missing
        """
        if publication.publisher_name is None:
            raise InvalidMetadataError("Monograph missing publisher name")
        publisher_id = self._match_or_create_publisher(publication.publisher_name)
        return publication.to_monograph_dto(publisher_id=publisher_id)

    def _enrich_funders(self, funding: list[PreviewExternalFunding]) -> list[FunderMatch]:
        matches = []
        for f in funding:
            doi = None
            for id_ in f.identifiers:
                try:
                    doi = Doi(id_)
                    break
                except ValueError:
                    continue

            if doi:
                resolved_funder = self.doi_client.fetch_funder(doi)
                matches.append(FunderMatch(name=resolved_funder.name, funder_doi=doi.value()))
            else:
                matches.append(FunderMatch(name=f.name, funder_doi=""))

        return matches

    def _resolve_external_funding(
        self, funding: list[PreviewExternalFunding]
    ) -> list[ExternalFundingDto]:
        matches = self._enrich_funders(funding)
        resolved = resolve_funders(matches)
        return [
            ExternalFundingDto(
                organization=r.organization_id,
                project_id=f.project_id,
                project_name="",
            )
            for f, r in zip(funding, resolved)
        ]

    def _convert_preview_to_creation_dto(
        self, preview: PreviewFundingRequest, override: OverrideImport
    ) -> CreateFundingRequestDto:
        """Convert preview DTO to creation DTO by resolving/creating database entities.

        When an override is provided, entity IDs are used directly (no lookup).
        Without override, journals and publishers are matched or created in the database.

        Args:
            preview: PreviewFundingRequest with publication metadata
            override: Override specifying entity IDs to use directly

        Returns:
            CreateFundingRequestDto with resolved database IDs

        Raises:
            InvalidMetadataError: If required metadata is missing
        """
        publication_dto: PublicationDto | MonographDto

        if override.overrides_to_article():
            if not isinstance(preview.publication, PreviewArticle):
                raise ValueError("Override type mismatch: expected PreviewArticle")
            publication_dto = preview.publication.to_publication_dto(override.journal_id)
        elif override.overrides_to_monograph():
            if not isinstance(preview.publication, PreviewMonograph):
                raise ValueError("Override type mismatch: expected PreviewMonograph")
            publication_dto = preview.publication.to_monograph_dto(override.publisher_id)
        else:
            match preview.publication:
                case PreviewArticle() as article:
                    publication_dto = self._resolve_article_dto(article)
                case PreviewMonograph() as monograph:
                    publication_dto = self._resolve_monograph_dto(monograph)

        return CreateFundingRequestDto(
            publication=publication_dto,
            payment=PaymentDto.empty(),
            extra_information=ExtraInformationDto(),
            funding=self._resolve_external_funding(preview.publication.funding),
        )

    def _match_or_create_publisher(self, publisher_name: str) -> PublisherId:
        """Match publisher by name or create a new one."""
        publisher = publisher_services.find_by_name(publisher_name)
        if publisher:
            return PublisherId(publisher.pk)

        return publisher_services.create(name=publisher_name)
