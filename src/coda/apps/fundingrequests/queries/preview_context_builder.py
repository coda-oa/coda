"""Context builder for DOI preview detail view.

Converts session-stored preview DTOs to detail models.
This allows reusing the existing fundingrequest_detail.html template structure.
"""

from functools import singledispatch
from typing import Any

from coda.apps.authors.dto import AuthorDto
from coda.apps.fundingrequests.models import FundingOrganization, FundingOrganizationLink
from coda.apps.institutions import repository as institution_repository
from coda.contexts.publication.dto.preview import (
    PreviewArticle,
    PreviewExternalFunding,
    PreviewFundingRequest,
    PreviewMonograph,
)
from coda.domain.author import Role
from coda.domain.orcid import Orcid
from coda.domain.publication.links import Doi, Isbn, Link

from .models import AuthorDetail, PublicationDetail, PublishingEntityInfo, UnpaidDetail


def tag_existing_funders(
    funding: list[PreviewExternalFunding],
) -> list[PreviewExternalFunding]:
    existing_dois = set(
        FundingOrganizationLink.objects.filter(type__name="DOI").values_list("value", flat=True)
    )
    existing_names = set(FundingOrganization.objects.values_list("name", flat=True))
    return [
        f.model_copy(
            update={
                "is_new": not (
                    f.name in existing_names or any(id_ in existing_dois for id_ in f.identifiers)
                )
            }
        )
        for f in funding
    ]


def build_preview_context(preview_fr: PreviewFundingRequest, session_key: str) -> dict[str, Any]:
    """Build template context from a PreviewFundingRequest DTO.

    Builds a preview-specific context WITHOUT creating database entities.
    Read-only lookups (e.g. institution names for authors) are performed but
    nothing is persisted. This is different from the regular detail view
    which uses actual persisted data.

    Args:
        preview_fr: PreviewFundingRequest DTO (already built by the view)
        session_key: Session key for identifying this preview

    Returns:
        Context dict compatible with fundingrequest_detail.html template
    """
    author_details = _build_author_details_from_dtos(preview_fr.publication.authors)
    publication_detail = _build_publication_detail_from_preview(
        preview_pub=preview_fr.publication,
        author_details=author_details,
    )

    current_type = (
        "article" if preview_fr.publication.publication_kind == "journal_article" else "monograph"
    )

    funding = tag_existing_funders(preview_fr.publication.funding)

    return {
        "session_key": session_key,
        "publication": publication_detail,
        "funding": funding,
        "funding_organizations": FundingOrganization.objects.all(),
        "is_preview": True,
        "current_publication_type": current_type,
        "warnings": preview_fr.warnings,
    }


def _build_publication_detail_from_preview(
    preview_pub: PreviewArticle | PreviewMonograph,
    author_details: list[AuthorDetail],
) -> PublicationDetail:
    """Build PublicationDetail directly from preview DTO without ORM lookups.

    Preview-specific: journal/publisher need not exist in the database.
    Publishing entity info is derived directly from the DTO.
    """
    entity_type, entity_name, identifier_name, identifier = _entity_info(preview_pub)

    links: list[Link] = [Doi(preview_pub.doi)]
    if isinstance(preview_pub, PreviewMonograph) and preview_pub.isbn:
        links.append(Isbn(preview_pub.isbn))

    return PublicationDetail(
        edit_url="",
        title=preview_pub.meta.title,
        request_remarks="",
        relevant_authors=author_details,
        other_authors=[],
        publishing_entity_type=entity_type,
        publishing_entity_name=entity_name,
        publishing_entity_identifier_name=identifier_name,
        publishing_entity_identifier=identifier,
        publication_state=preview_pub.meta.publication_state,
        online_publication_date=preview_pub.meta.online_publication_date,
        print_publication_date=preview_pub.meta.print_publication_date,
        license=preview_pub.meta.license,
        publication_type=preview_pub.meta.publication_type.name,
        subject_area=preview_pub.meta.subject_area.name,
        oa_type=preview_pub.meta.open_access_type,
        references=links,
        contracts=[],
        payment_details=UnpaidDetail(),
    )


@singledispatch
def _entity_info(
    preview_pub: PreviewArticle | PreviewMonograph,
) -> PublishingEntityInfo:
    raise NotImplementedError(f"Unsupported publication type: {type(preview_pub)}")


@_entity_info.register
def _(article: PreviewArticle) -> PublishingEntityInfo:
    if article.journal is None:
        return PublishingEntityInfo("Journal", "(journal not specified)", "", "")

    name = article.journal.title
    if article.publisher_name:
        name = f"{name}, {article.publisher_name}"

    return PublishingEntityInfo(
        "Journal", name, "EISSN" if article.journal.eissn else "", article.journal.eissn or ""
    )


@_entity_info.register
def _(monograph: PreviewMonograph) -> PublishingEntityInfo:
    return PublishingEntityInfo(
        "Publisher", monograph.publisher_name or "(publisher not specified)", "", ""
    )


def _build_author_details_from_dtos(author_dtos: list[AuthorDto]) -> list[AuthorDetail]:
    """Convert AuthorDtos to AuthorDetails with affiliation names resolved (single query)."""
    affiliation_ids = [dto.affiliation for dto in author_dtos if dto.affiliation]
    institutions = {
        inst.pk: inst.name for inst in institution_repository.get_many_by_id(affiliation_ids)
    }

    result = []
    for dto in author_dtos:
        affiliation_name = ""
        if dto.affiliation:
            affiliation_name = institutions.get(dto.affiliation, f"Unknown ({dto.affiliation})")

        result.append(
            AuthorDetail(
                name=dto.name,
                email=dto.email or "",
                affiliation=affiliation_name,
                role=Role[dto.role] if dto.role else Role.CO_AUTHOR,
                orcid=Orcid(dto.orcid) if dto.orcid else None,
            )
        )

    return result
