from django.db import transaction

from coda.apps.fundingrequests.models import ExternalFunding
from coda.apps.fundingrequests.models import FundingOrganization as FundingOrganizationModel
from coda.apps.fundingrequests.models import FundingOrganizationLink
from coda.contexts.fundingrequest.services.funder_resolution import (
    FundingOrganization,
    enrich_from_ror,
)
from coda.contexts.fundingrequest.services.funder_resolution.ror_client import RORClient
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId


def can_delete_funding_organization(org: FundingOrganizationModel) -> tuple[bool, list[str]]:
    blocking: list[str] = []
    if org.archived_at:
        blocking.append("Funding organization is archived and must be restored before deletion")
        return len(blocking) == 0, blocking
    funding_count = ExternalFunding.objects.filter(organization=org).count()
    if funding_count > 0:
        blocking.append(f"{funding_count} funding request(s) reference this organization")
    return len(blocking) == 0, blocking


def archive_funding_organization(org: FundingOrganizationModel) -> None:
    if org.archived_at:
        raise ValueError("Funding organization is already archived")
    org.archive()


def restore_funding_organization(org: FundingOrganizationModel) -> None:
    if not org.archived_at:
        raise ValueError("Funding organization is not archived")
    org.restore()


def delete_funding_organization(org: FundingOrganizationModel) -> None:
    can_delete, reasons = can_delete_funding_organization(org)
    if not can_delete:
        raise ValueError(f"Cannot delete funding organization: {', '.join(reasons)}")
    org.delete()


def update_funder_from_ror(
    funder_id: FundingOrganizationId,
    ror_client: RORClient,
) -> bool:
    """Update funding organization from ROR.

    Returns True if links were changed, False otherwise.
    """
    org = FundingOrganizationModel.objects.get(pk=funder_id)

    api_result = ror_client.resolve_by_ids(org.get_links())
    funder = FundingOrganization(name=org.name, links=tuple(org.get_links()))
    enriched = enrich_from_ror(funder, api_result)

    links_changed = enriched.links != tuple(org.get_links())
    if enriched.name != org.name or links_changed:
        org.name = enriched.name
        org.set_links(enriched.links)
        org.save()

    return links_changed


@transaction.atomic
def merge_funding_organizations(
    source: FundingOrganizationModel,
    target: FundingOrganizationModel,
) -> None:
    if source.pk == target.pk:
        raise ValueError("Cannot merge organization into itself")

    if source.archived_at:
        raise ValueError("Cannot merge an archived organization")

    if target.archived_at:
        raise ValueError("Cannot merge into an archived organization")

    # Move all ExternalFunding records from source to target
    ExternalFunding.objects.filter(organization=source).update(organization=target)

    # Merge links from source to target (target takes priority)
    source_links = source.get_links()
    target_links = target.get_links()
    merged_funder = FundingOrganization(
        name=target.name,
        links=tuple(source_links),
    )
    merged_funder = merged_funder.revised(links=target_links)
    target.set_links(merged_funder.links)

    # Delete the source organization
    source.delete()


def find_overlapping_organizations(
    organization: FundingOrganizationModel,
) -> list[FundingOrganizationModel]:
    links = organization.get_links()
    if not links:
        return []

    overlapping_links = FundingOrganizationLink.objects.find_by_links(links)
    overlapping_org_ids = {
        link.funding_organization_id
        for link in overlapping_links
        if link.funding_organization_id != organization.pk
    }

    return list(FundingOrganizationModel.objects.filter(pk__in=overlapping_org_ids).distinct())


def search_organizations_for_merge(
    query: str,
    exclude_pk: int,
) -> list[FundingOrganizationModel]:
    # Search by name (case-insensitive partial match)
    name_matches = FundingOrganizationModel.objects.filter(
        name__icontains=query,
    ).exclude(pk=exclude_pk)

    # Search by link value (exact match)
    link_matches = FundingOrganizationModel.objects.filter(
        links__value=query,
    ).exclude(pk=exclude_pk)

    # Combine results and exclude archived organizations
    combined_pks = set(name_matches.values_list("pk", flat=True)) | set(
        link_matches.values_list("pk", flat=True)
    )

    return list(
        FundingOrganizationModel.objects.filter(pk__in=combined_pks)
        .filter(archived_at__isnull=True)
        .distinct()
    )


def can_merge_funding_organization(
    source: FundingOrganizationModel,
    target: FundingOrganizationModel,
) -> tuple[bool, list[str]]:
    blocking: list[str] = []

    if source.pk == target.pk:
        blocking.append("Cannot merge organization into itself")

    if source.archived_at:
        blocking.append("Cannot merge an archived organization")

    if target.archived_at and target.pk != source.pk:
        blocking.append("Cannot merge into an archived organization")

    return len(blocking) == 0, blocking
