"""Funder enrichment via ROR — model-free domain logic.

Provides the ``enrich`` function to enrich a domain
``FunderRecord`` with ROR API results, independent of any
persistence layer.
"""

import logging
from collections.abc import Iterable

from coda.domain.fundingrequest import FunderRecord
from coda.domain.publication.links import Link

from .ror_client import RORRecord

logger = logging.getLogger(__name__)


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
    funder: FunderRecord,
    ror_results: dict[str, RORRecord],
) -> FunderRecord:
    """Enrich a FunderRecord with ROR data, returning a new FunderRecord.

    Returns the original FunderRecord unchanged when no ROR record matches
    or when ROR record conversion fails.
    """
    record = _find_ror_record(funder.links, ror_results)
    if record is None:
        return funder
    try:
        return funder.revised(name=record.name, links=record.to_links())
    except Exception:
        logger.debug("ROR record conversion failed", exc_info=True)
        return funder
