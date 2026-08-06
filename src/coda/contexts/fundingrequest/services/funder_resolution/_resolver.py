"""Service for resolving external funding metadata to DB entities.

Handles the identifier → organization match, bulk creation of missing funding
organizations, and persistence of funder links so future imports can match
by either identifier even when the funder name differs.

Identifiers are modelled as the domain ``Link`` types (``Doi``,
``CrossrefId``) from ``coda.domain.publication.links`` — the resolver
never deals with raw identifier strings, and resolves the DB link type from
each link's own ``type()``.
"""

import logging
from functools import reduce

from coda.apps.fundingrequests.models import FundingOrganization as FundingOrganizationModel
from coda.apps.fundingrequests.models import FundingOrganizationLink
from coda.domain.fundingrequest import FunderRecord, FundingOrganizationId

from .enrichment import enrich_from_ror
from .ror_client import CachingRORClient, RORClient, RORRecord

logger = logging.getLogger(__name__)


def resolve_funders(
    funders: list[FunderRecord],
    ror_client: RORClient | CachingRORClient | None = None,
) -> list[FunderRecord]:
    """Match funders by identifier (DOI preferred, then Crossref ID), then by name.

    When ``ror_client`` is provided, each ``FunderRecord`` is first enriched
    via ROR: its links are resolved to a ROR record, the ROR links are merged in,
    and the funder name is updated to the canonical ROR name (falling back to the
    metadata name when ROR resolution fails for the whole batch). Enrichment is
    skipped entirely when ``ror_client`` is ``None``.

    Creates missing funding organizations and persists DOI, Crossref and ROR
    links so future imports can match by either identifier even when the funder
    name differs.

    Returns one ``FunderRecord`` per input, with ``organization_id``
    populated, preserving order.
    """
    if ror_client is not None:
        funders = _enrich_with_ror(funders, ror_client)

    matched = _match_existing_links(funders)
    name_to_org = _resolve_organizations(funders, matched)

    resolved = _build_resolved_funders(funders, name_to_org)
    _persist_new_links(resolved)

    return resolved


def _enrich_with_ror(
    funders: list[FunderRecord],
    ror_client: RORClient | CachingRORClient,
) -> list[FunderRecord]:
    """Enrich funders with ROR data, falling back to metadata names on failure.

    Resolves all funder links in a single batch ROR call. For each funder
    whose links match a ROR record, the canonical ROR name is used and
    ROR links are merged in. On a batch-level ROR failure, logs a warning
    and keeps the original metadata names and links.
    """
    all_links = [link for f in funders for link in f.links]
    ror_results: dict[str, RORRecord] = {}
    if all_links:
        try:
            ror_results = ror_client.resolve_by_ids(all_links)
        except Exception:
            logger.warning(
                "ROR resolution failed — falling back to metadata names",
                exc_info=True,
            )

    return [enrich_from_ror(f, ror_results) for f in funders]


def _match_existing_links(
    funders: list[FunderRecord],
) -> dict[tuple[str, str], FundingOrganizationModel]:
    all_links = [link for f in funders for link in f.links]
    if not all_links:
        return {}

    existing = FundingOrganizationLink.objects.find_by_links(all_links)
    return {(link.type.name, link.value): link.funding_organization for link in existing}


def _resolve_organizations(
    funders: list[FunderRecord],
    matched: dict[tuple[str, str], FundingOrganizationModel],
) -> dict[str, FundingOrganizationModel]:
    name_to_org: dict[str, FundingOrganizationModel] = {}
    for f in funders:
        for link in f.links:
            if (link.type(), link.value()) in matched:
                name_to_org[f.name] = matched[(link.type(), link.value())]
                break

    unmatched = [f for f in funders if f.name not in name_to_org]
    name_to_org.update(_match_or_create_by_name(unmatched))

    return name_to_org


def _match_or_create_by_name(
    funders: list[FunderRecord],
) -> dict[str, FundingOrganizationModel]:
    names = {f.name for f in funders}
    return FundingOrganizationModel.objects.bulk_get_or_create_by_name(names)


def _persist_new_links(resolved: list[FunderRecord]) -> None:
    """Fold funder links per org using domain logic, then persist.

    Fetches all target organizations in a single bulk query.
    """
    org_ids = {f.organization_id for f in resolved if f.organization_id is not None}
    if not org_ids:
        return

    orgs = FundingOrganizationModel.objects.in_bulk(org_ids)

    for org_id in org_ids:
        org_funders = [f for f in resolved if f.organization_id == org_id]
        merged = reduce(lambda a, b: a.revised(links=b.links), org_funders)
        orgs[org_id].set_links(merged.links)


def _build_resolved_funders(
    funders: list[FunderRecord],
    name_to_org: dict[str, FundingOrganizationModel],
) -> list[FunderRecord]:
    return [
        f.with_id(organization_id=FundingOrganizationId(name_to_org[f.name].pk)) for f in funders
    ]
