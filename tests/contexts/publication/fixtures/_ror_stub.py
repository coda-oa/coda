"""Stub ROR client for seam tests.

Returns a known RORRecord for a specific Crossref ID so ROR resolution can be
exercised through the import seams without hitting the live ROR API.
"""

from collections.abc import Sequence

from coda.contexts.publication.services.doi_client._ror import RORClient, RORRecord
from coda.domain.publication.links import Link

HZDR_ROR = "https://ror.org/05dxps055"
HZDR_CROSSREF = "501100008346"
HZDR_NAME = "Helmholtz-Zentrum Dresden-Rossendorf"


class StubRORClient(RORClient):
    """Stub that resolves Crossref id ``HZDR_CROSSREF`` to a known ROR record."""

    def resolve_by_ids(self, links: Sequence[Link]) -> dict[str, RORRecord]:
        return {
            str(link): RORRecord(
                id=HZDR_ROR,
                name=HZDR_NAME,
                external_ids={"Crossref": [HZDR_CROSSREF]},
            )
            for link in links
            if str(link) == HZDR_CROSSREF
        }
