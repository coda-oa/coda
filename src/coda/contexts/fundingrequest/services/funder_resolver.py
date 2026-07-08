"""Service for resolving external funding metadata to DB entities.

Handles the two-phase match (DOI → name), bulk creation of missing funding
organizations, and persistence of DOI links for future matches.
"""

from dataclasses import dataclass
from typing import NamedTuple

from coda.apps.fundingrequests.models import (
    FundingOrganization,
    FundingOrganizationLink,
    FundingOrganizationLinkType,
)
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId


@dataclass(frozen=True, slots=True)
class FunderMatch:
    name: str
    funder_doi: str
    crossref_id: str = ""


@dataclass(frozen=True)
class ResolvedFunder:
    funder: FunderMatch
    organization_id: FundingOrganizationId


class _MatchByDOIResult(NamedTuple):
    matched: dict[str, FundingOrganization]
    remaining: list[FunderMatch]


def resolve_funders(
    funders: list[FunderMatch],
) -> list[ResolvedFunder]:
    """Match funders by DOI (preferred), then by Crossref ID, then by name.

    Creates missing funding organizations and persists DOI and Crossref links
    so future imports can match by either identifier even when the funder name
    differs.

    Returns one ResolvedFunder per input FunderMatch, preserving order.
    """
    doi_type = FundingOrganizationLinkType.objects.get(name="DOI")
    crossref_type = FundingOrganizationLinkType.objects.get(name="Crossref")

    matched_by_doi, remaining = _match_by_doi(funders, doi_type)
    matched_by_crossref, remaining = _match_by_crossref(remaining, crossref_type)
    matched_by_doi.update(matched_by_crossref)

    name_to_org = _build_name_lookup(remaining, matched_by_doi)

    _persist_new_doi_links(doi_type, funders, matched_by_doi, name_to_org)
    _persist_new_crossref_links(crossref_type, funders, matched_by_doi, name_to_org)

    return _build_resolved_funders(funders, name_to_org)


def _match_by_doi(
    funders: list[FunderMatch],
    doi_type: FundingOrganizationLinkType,
) -> _MatchByDOIResult:
    doi_to_funder = {f.funder_doi: f for f in funders if f.funder_doi}
    links = FundingOrganizationLink.objects.filter(
        type=doi_type, value__in=list(doi_to_funder.keys())
    ).select_related("funding_organization")
    matched = {link.value: link.funding_organization for link in links}
    remaining = [f for doi, f in doi_to_funder.items() if doi not in matched]
    remaining.extend(f for f in funders if not f.funder_doi)
    return _MatchByDOIResult(matched=matched, remaining=remaining)


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


def _build_name_lookup(
    remaining: list[FunderMatch],
    matched_by_doi: dict[str, FundingOrganization],
) -> dict[str, FundingOrganization]:
    name_to_org = _match_or_create_by_name(remaining)
    for org in matched_by_doi.values():
        name_to_org[org.name] = org
    return name_to_org


def _persist_new_doi_links(
    doi_type: FundingOrganizationLinkType,
    funders: list[FunderMatch],
    matched_by_doi: dict[str, FundingOrganization],
    name_to_org: dict[str, FundingOrganization],
) -> None:
    links = [
        FundingOrganizationLink(
            type=doi_type,
            value=f.funder_doi,
            funding_organization=name_to_org[f.name],
        )
        for f in funders
        if f.funder_doi and f.funder_doi not in matched_by_doi
    ]
    FundingOrganizationLink.objects.bulk_create(links, ignore_conflicts=True)


def _match_by_crossref(
    funders: list[FunderMatch],
    crossref_type: FundingOrganizationLinkType,
) -> _MatchByDOIResult:
    crossref_to_funder = {f.crossref_id: f for f in funders if f.crossref_id}
    if not crossref_to_funder:
        return _MatchByDOIResult(matched={}, remaining=funders)
    links = FundingOrganizationLink.objects.filter(
        type=crossref_type, value__in=list(crossref_to_funder.keys())
    ).select_related("funding_organization")
    matched = {link.value: link.funding_organization for link in links}
    remaining = [f for cid, f in crossref_to_funder.items() if cid not in matched]
    remaining.extend(f for f in funders if not f.crossref_id)
    return _MatchByDOIResult(matched=matched, remaining=remaining)


def _persist_new_crossref_links(
    crossref_type: FundingOrganizationLinkType,
    funders: list[FunderMatch],
    matched_by_doi: dict[str, FundingOrganization],
    name_to_org: dict[str, FundingOrganization],
) -> None:
    links = [
        FundingOrganizationLink(
            type=crossref_type,
            value=f.crossref_id,
            funding_organization=name_to_org[f.name],
        )
        for f in funders
        if f.crossref_id and f.crossref_id not in matched_by_doi
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
