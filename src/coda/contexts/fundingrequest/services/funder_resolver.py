"""Service for resolving external funding metadata to DB entities.

Handles the identifier → organization match, bulk creation of missing funding
organizations, and persistence of funder links so future imports can match
by either identifier even when the funder name differs.

Identifiers are modelled as the domain ``Link`` types (``Doi``,
``CrossrefId``) from ``coda.domain.publication.links`` — the resolver
never deals with raw identifier strings, and resolves the DB link type from
each link's own ``type()``.
"""

from dataclasses import dataclass

from coda.apps.fundingrequests.models import (
    FundingOrganization,
    FundingOrganizationLink,
    FundingOrganizationLinkType,
)
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId, Doi, Link


@dataclass(frozen=True, slots=True)
class FunderMatch:
    name: str
    links: tuple[Link, ...] = ()


@dataclass(frozen=True)
class ResolvedFunder:
    funder: FunderMatch
    organization_id: FundingOrganizationId


def resolve_funders(
    funders: list[FunderMatch],
) -> list[ResolvedFunder]:
    """Match funders by identifier (DOI preferred, then Crossref ID), then by name.

    Creates missing funding organizations and persists DOI and Crossref links
    so future imports can match by either identifier even when the funder name
    differs.

    Returns one ResolvedFunder per input FunderMatch, preserving order.
    """
    link_types = _link_types()
    matched = _match_existing_links(link_types, funders)
    name_to_org = _resolve_organizations(funders, matched)

    _persist_new_links(link_types, funders, matched, name_to_org)

    return _build_resolved_funders(funders, name_to_org)


def _link_types() -> dict[str, FundingOrganizationLinkType]:
    """Map each supported link type name to its DB row.

    Uses the domain ``Link.type()`` so the string coupling to the seeded
    ``FundingOrganizationLinkType`` rows lives only in the domain.
    """
    names = [Doi.type(), CrossrefId.type(), Ror.type()]
    return {t.name: t for t in FundingOrganizationLinkType.objects.filter(name__in=names)}


def _match_existing_links(
    link_types: dict[str, FundingOrganizationLinkType],
    funders: list[FunderMatch],
) -> dict[tuple[str, str], FundingOrganization]:
    all_links = [link for f in funders for link in f.links]
    if not all_links:
        return {}

    existing = FundingOrganizationLink.objects.filter(
        type__name__in=list(link_types.keys()),
        value__in=[link.value() for link in all_links],
    ).select_related("funding_organization")
    return {(link.type.name, link.value): link.funding_organization for link in existing}


def _resolve_organizations(
    funders: list[FunderMatch],
    matched: dict[tuple[str, str], FundingOrganization],
) -> dict[str, FundingOrganization]:
    name_to_org: dict[str, FundingOrganization] = {}
    for f in funders:
        for link in f.links:
            if (link.type(), link.value()) in matched:
                name_to_org[f.name] = matched[(link.type(), link.value())]
                break

    unmatched = [f for f in funders if f.name not in name_to_org]
    name_to_org.update(_match_or_create_by_name(unmatched))

    for f in funders:
        if f.name not in name_to_org:
            org, _ = FundingOrganization.objects.get_or_create(name=f.name)
            name_to_org[f.name] = org

    return name_to_org


def _match_or_create_by_name(
    funders: list[FunderMatch],
) -> dict[str, FundingOrganization]:
    names = list({f.name for f in funders})
    existing = {
        e.name: e for e in FundingOrganization.objects.filter(name__in=names).only("pk", "name")
    }
    names_to_create = set(names) - set(existing.keys())
    created = FundingOrganization.objects.bulk_create(
        FundingOrganization(name=n) for n in names_to_create
    )
    result = dict(existing)
    for org in created:
        result[org.name] = org
    return result


def _persist_new_links(
    link_types: dict[str, FundingOrganizationLinkType],
    funders: list[FunderMatch],
    matched: dict[tuple[str, str], FundingOrganization],
    name_to_org: dict[str, FundingOrganization],
) -> None:
    """Create one link per (type, value, org) not already persisted.

    Dedupes within the batch (a funder appearing multiple times in
    ``funders`` — the mass-import path aggregates every DOI's matches
    into one call — yields a single link per type) and skips identifiers
    already in ``matched``. ``ignore_conflicts`` guards against races on
    re-import.
    """
    candidates = [
        (link_types[link.type()], link.value(), name_to_org[f.name])
        for f in funders
        for link in f.links
        if link.type() in link_types
        if (link.type(), link.value()) not in matched
    ]
    unique = list(dict.fromkeys(candidates))
    links = [
        FundingOrganizationLink(type=link_type, value=value, funding_organization=org)
        for link_type, value, org in unique
    ]
    FundingOrganizationLink.objects.bulk_create(links, ignore_conflicts=True)


def _build_resolved_funders(
    funders: list[FunderMatch],
    name_to_org: dict[str, FundingOrganization],
) -> list[ResolvedFunder]:
    return [
        ResolvedFunder(
            funder=f,
            organization_id=FundingOrganizationId(name_to_org[f.name].pk),
        )
        for f in funders
    ]
