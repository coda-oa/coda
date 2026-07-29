from coda.apps.fundingrequests.models import ExternalFunding
from coda.apps.fundingrequests.models import FundingOrganization as FundingOrganizationModel
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
) -> None:
    org = FundingOrganizationModel.objects.get(pk=funder_id)

    api_result = ror_client.resolve_by_ids(org.get_links())
    funder = FundingOrganization(name=org.name, links=tuple(org.get_links()))
    enriched = enrich_from_ror(funder, api_result)

    if enriched.name != org.name or enriched.links != tuple(org.get_links()):
        org.name = enriched.name
        org.set_links(enriched.links)
        org.save()
