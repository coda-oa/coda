"""Funder enrichment via ROR — model-free domain logic.

Provides the ``enrich`` function to enrich a domain
``FundingOrganization`` with ROR API results, independent of any
persistence layer.
"""

from collections.abc import Iterable

from coda.domain.fundingrequest import FundingOrganization
from coda.domain.publication.links import Link

from .ror_client import RORRecord


def _find_ror_record(
    links: Iterable[Link],
    api_result: dict[str, RORRecord],
) -> RORRecord | None:
    """Find the first ROR record matching any of the given links."""
    for link in links:
        record = api_result.get(link.value())
        if record is not None:
            return record
    return None


def enrich_from_ror(
    funder: FundingOrganization,
    ror_results: dict[str, RORRecord],
) -> FundingOrganization:
    """Enrich a FundingOrganization with ROR data, returning a new FundingOrganization.

    Returns the original FundingOrganization unchanged when no ROR record matches
    or when ROR record conversion fails.
    """
    record = _find_ror_record(funder.links, ror_results)
    if record is None:
        return funder
    try:
        return funder.revised(name=record.name, links=record.to_links())
    except Exception:
        return funder
