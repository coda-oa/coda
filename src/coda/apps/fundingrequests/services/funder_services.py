from coda.apps.fundingrequests.models import ExternalFunding, FundingOrganization


def can_delete_funding_organization(org: FundingOrganization) -> tuple[bool, list[str]]:
    blocking: list[str] = []
    funding_count = ExternalFunding.objects.filter(organization=org).count()
    if funding_count > 0:
        blocking.append(f"{funding_count} funding request(s) reference this organization")
    return len(blocking) == 0, blocking


def archive_funding_organization(org: FundingOrganization) -> None:
    if org.archived_at:
        raise ValueError("Funding organization is already archived")
    org.archive()


def restore_funding_organization(org: FundingOrganization) -> None:
    if not org.archived_at:
        raise ValueError("Funding organization is not archived")
    org.restore()


def delete_funding_organization(org: FundingOrganization) -> None:
    can_delete, reasons = can_delete_funding_organization(org)
    if not can_delete:
        raise ValueError(f"Cannot delete funding organization: {', '.join(reasons)}")
    org.delete()
