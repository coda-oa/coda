"""DOI Import Service - Creates FundingRequests from DOI metadata."""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests.models import FundingOrganization
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
from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalJournal,
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
from coda.domain.author import Role
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.issn import Issn
from coda.domain.orcid import Orcid
from coda.domain.publication import JournalId
from coda.domain.publication.links import Doi
from coda.domain.string import NonEmptyStr

from ._map_to_preview import build_preview_article, build_preview_monograph


@dataclass(frozen=True)
class OverrideImportAsArticle:
    journal_id: JournalId


@dataclass(frozen=True)
class OverrideImportAsMonograph:
    publisher_id: PublisherId


OverrideImportPublicationType = OverrideImportAsArticle | OverrideImportAsMonograph


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
        metadata = self._fetch_metadata(doi)
        detected_type = detect_publication_type(metadata)
        authors_dto = self._build_authors_dto(metadata.authors)

        publication_preview: PreviewArticle | PreviewMonograph
        match detected_type:
            case "article":
                publication_preview = build_preview_article(doi, metadata, authors_dto)
            case "monograph":
                publication_preview = build_preview_monograph(doi, metadata, authors_dto)

        return PreviewFundingRequest(publication=publication_preview)

    def build_preview_with_type_override(
        self, doi: Doi, override: OverrideImportPublicationType
    ) -> PreviewFundingRequest:
        """Build a preview with an explicit publication type override.

        Fetches metadata from cache (no Crossref re-fetch), resolves the selected
        journal or publisher by DB ID, and builds the appropriate preview DTO.
        """
        metadata = self._fetch_metadata(doi)
        authors_dto = self._build_authors_dto(metadata.authors)

        publication: PreviewArticle | PreviewMonograph
        match override:
            case OverrideImportAsArticle(journal_id=journal_id):
                journal = journal_services.get_by_pk(int(journal_id))
                overridden_metadata = metadata.model_copy(
                    update={
                        "journal": ExternalJournal(
                            title=journal.title,
                            issn=None,
                            eissn=journal.eissn,
                        )
                    }
                )
                publication = build_preview_article(doi, overridden_metadata, authors_dto)
            case OverrideImportAsMonograph(publisher_id=publisher_id):
                publisher = publisher_services.get_by_pk(int(publisher_id))
                overridden_metadata = metadata.model_copy(update={"publisher": publisher.name})
                publication = build_preview_monograph(doi, overridden_metadata, authors_dto)

        return PreviewFundingRequest(publication=publication)

    def import_from_doi(
        self, doi: Doi, override: OverrideImportPublicationType | None = None
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

        match override:
            case OverrideImportAsArticle() | OverrideImportAsMonograph():
                preview_dto = self.build_preview_with_type_override(doi, override)
            case None:
                preview_dto = self.fetch_doi_preview(doi)

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

    def _resolve_funders(self, funding: list[PreviewExternalFunding]) -> list[_ResolvedFunding]:
        resolved_funding = []
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
                resolved_funding.append(
                    _ResolvedFunding(f.name, resolved_funder.name, doi.value(), f.project_id)
                )
            else:
                resolved_funding.append(_ResolvedFunding(f.name, "", "", f.project_id))

        return resolved_funding

    def _resolve_external_funding(
        self, funding: list[PreviewExternalFunding]
    ) -> list[ExternalFundingDto]:
        resolved_funding = self._resolve_funders(funding)

        names = {f.name for f in resolved_funding}
        existing = FundingOrganization.objects.filter(name__in=names).only("pk", "name").all()
        existing_names = {e.name for e in existing}
        funders_to_create: set[str] = names.difference(existing_names)
        created_funders = FundingOrganization.objects.bulk_create(
            FundingOrganization(name=f) for f in funders_to_create
        )
        all_funders = itertools.chain(existing, created_funders)
        names_to_pks = {f.name: f.pk for f in all_funders}

        return [
            ExternalFundingDto(
                organization=FundingOrganizationId(names_to_pks[f.name]),
                project_id=f.project_id,
                project_name="",
            )
            for f in resolved_funding
        ]

    def _convert_preview_to_creation_dto(
        self,
        preview: PreviewFundingRequest,
        override: OverrideImportPublicationType | None = None,
    ) -> CreateFundingRequestDto:
        """Convert preview DTO to creation DTO by resolving/creating database entities.

        When an override is provided, entity IDs are used directly (no lookup).
        Without override, journals and publishers are matched or created in the database.

        Args:
            preview: PreviewFundingRequest with publication metadata
            override: Optional override specifying entity IDs to use directly

        Returns:
            CreateFundingRequestDto with resolved database IDs

        Raises:
            InvalidMetadataError: If required metadata is missing
        """
        publication_dto: PublicationDto | MonographDto

        match override:
            case OverrideImportAsArticle(journal_id=journal_id):
                if not isinstance(preview.publication, PreviewArticle):
                    raise ValueError("Override type mismatch: expected PreviewArticle")
                publication_dto = preview.publication.to_publication_dto(journal_id=journal_id)

            case OverrideImportAsMonograph(publisher_id=publisher_id):
                if not isinstance(preview.publication, PreviewMonograph):
                    raise ValueError("Override type mismatch: expected PreviewMonograph")
                publication_dto = preview.publication.to_monograph_dto(publisher_id=publisher_id)

            case None:
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

    def _build_authors_dto(self, external_authors: list[ExternalAuthor]) -> list[AuthorDto]:
        """Convert external author metadata to AuthorDto objects."""
        authors = []

        for external_author in external_authors:
            normalized_name = self._normalize_author_name(
                external_author.name,
                external_author.affiliation,
                external_author.ror_id,
            )
            if normalized_name is None:
                continue

            orcid = None
            if external_author.orcid:
                orcid = Orcid(external_author.orcid)

            authors.append(
                AuthorDto(
                    name=normalized_name,
                    email="",
                    orcid=orcid,
                    affiliation=None,
                    role=Role.CO_AUTHOR.name,
                )
            )

        return authors

    def _normalize_author_name(
        self, name: str, affiliation: str | None, ror_id: str | None
    ) -> str | None:
        """Normalize author name, returning None if author should be skipped.

        Returns the trimmed name if valid, "Unknown" if name is empty but other data exists,
        or None if author has no usable data.
        """
        small_space = "\u2009"
        trimmed_name = name.strip().replace(small_space, " ")

        has_other_data = affiliation is not None or ror_id is not None

        if trimmed_name:
            return trimmed_name
        elif has_other_data:
            return "Unknown"
        else:
            return None

    def _match_or_create_publisher(self, publisher_name: str) -> PublisherId:
        """Match publisher by name or create a new one."""
        publisher = publisher_services.find_by_name(publisher_name)
        if publisher:
            return PublisherId(publisher.pk)

        return publisher_services.create(name=publisher_name)


@dataclass(frozen=True, slots=True)
class _ResolvedFunding:
    referenced_funder_name: str
    updated_funder_name: str
    funder_doi: str
    project_id: str

    @property
    def name(self) -> str:
        if self.updated_funder_name:
            return self.updated_funder_name

        return self.referenced_funder_name
