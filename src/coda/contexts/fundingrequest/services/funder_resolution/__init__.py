"""Funder resolution - ROR API client and funder matching logic.

Provides:
- ``RORClient`` / ``CachingRORClient`` — HTTP client for the ROR API
- ``resolve_funders`` — match funder metadata to database organizations
- ``enrich`` — enrich domain ``FundingOrganization`` with ROR data
"""

from coda.domain.fundingrequest import FundingOrganization as FundingOrganization

from ._resolver import resolve_funders as resolve_funders
from .enrichment import enrich_from_ror as enrich_from_ror
from .ror_client import CachingRORClient as CachingRORClient
from .ror_client import RORClient as RORClient
from .ror_client import RORClientError as RORClientError
from .ror_client import RORRecord as RORRecord

__all__ = [
    "CachingRORClient",
    "enrich_from_ror",
    "FundingOrganization",
    "RORClient",
    "RORClientError",
    "RORRecord",
    "resolve_funders",
]
