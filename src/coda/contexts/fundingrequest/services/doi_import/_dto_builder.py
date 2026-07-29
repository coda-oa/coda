"""Shared DTO builder for DOI import.

Builds a ``CreateFundingRequestDto`` from metadata-level preview data
and a ``DOIRepository`` for DB resolution.  Both the immediate and
unit-of-work repository implementations use this builder so that the
journal/publisher/funder resolution logic lives in one place.
"""

from __future__ import annotations

from coda.apps.publications.dto import MonographDto, PublicationDto
from coda.contexts.fundingrequest.dto.commands import (
    CreateFundingRequestDto,
    ExternalFundingDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.domain.fundingrequest import FundingOrganization
from coda.contexts.fundingrequest.dto.preview import (
    PreviewArticle,
    PreviewFundingRequest,
    PreviewMonograph,
)
from coda.contexts.fundingrequest.services.doi_import._service import (
    DOIRepository,
    OverrideImport,
)
from coda.contexts.fundingrequest.services.doi_import.errors import InvalidMetadataError
from coda.domain.contract import PublisherId
from coda.domain.issn import Issn
from coda.domain.publication import JournalId
from coda.domain.string import NonEmptyStr


def build_creation_dto(
    repo: DOIRepository,
    resolved: list[FundingOrganization],
    preview: PreviewFundingRequest,
    override: OverrideImport,
) -> CreateFundingRequestDto:
    """Build a ``CreateFundingRequestDto`` from preview metadata.

    Resolves journals and publishers through *repo*; funders are passed in
    already resolved so the caller controls when resolution happens.
    """
    pub_dto = _resolve_publication(repo, preview, override)

    funding = [
        ExternalFundingDto(
            organization=rf.organization_id,
            project_id=_project_id(preview, i),
            project_name="",
        )
        for i, rf in enumerate(resolved)
    ]

    return CreateFundingRequestDto(
        publication=pub_dto,
        payment=PaymentDto.empty(),
        extra_information=ExtraInformationDto(),
        funding=funding,
    )


def _project_id(preview: PreviewFundingRequest, idx: int) -> str:
    preview_funding = list(preview.publication.funding)
    return preview_funding[idx].project_id if idx < len(preview_funding) else ""


def _resolve_publication(
    repo: DOIRepository,
    preview: PreviewFundingRequest,
    override: OverrideImport,
) -> PublicationDto | MonographDto:
    if override.overrides_to_article():
        if not isinstance(preview.publication, PreviewArticle):
            raise ValueError("Override type mismatch: expected PreviewArticle")
        return preview.publication.to_publication_dto(override.journal_id)

    if override.overrides_to_monograph():
        if not isinstance(preview.publication, PreviewMonograph):
            raise ValueError("Override type mismatch: expected PreviewMonograph")
        return preview.publication.to_monograph_dto(override.publisher_id)

    match preview.publication:
        case PreviewArticle() as article:
            journal_id = _match_or_create_journal(repo, article)
            return article.to_publication_dto(journal_id=journal_id)
        case PreviewMonograph() as monograph:
            publisher_id = _match_or_create_publisher(repo, monograph.publisher_name)
            return monograph.to_monograph_dto(publisher_id=publisher_id)
        case _:
            raise InvalidMetadataError("Unknown publication type in preview")


def _match_or_create_journal(repo: DOIRepository, article: PreviewArticle) -> JournalId:
    if article.journal is None:
        raise InvalidMetadataError("Journal article missing journal metadata")
    if article.journal.eissn is None:
        raise InvalidMetadataError(f"Journal '{article.journal.title}' missing E-ISSN")

    issn = Issn(article.journal.eissn)
    journal = repo.find_journal_by_eissn(issn)
    if journal is not None:
        return JournalId(journal.pk)

    if not article.journal.title:
        raise InvalidMetadataError("Journal missing title")
    if article.publisher_name is None:
        raise InvalidMetadataError("Journal missing publisher name")

    publisher_id = _match_or_create_publisher(repo, article.publisher_name)
    return repo.create_journal(
        title=NonEmptyStr(article.journal.title), eissn=issn, publisher_id=publisher_id
    )


def _match_or_create_publisher(repo: DOIRepository, publisher_name: str | None) -> PublisherId:
    if publisher_name is None:
        raise InvalidMetadataError("Monograph missing publisher name")
    publisher = repo.find_publisher_by_name(publisher_name)
    if publisher is not None:
        return PublisherId(publisher.pk)
    return repo.create_publisher(name=publisher_name)
