"""Funder resolution - ROR API client and funder matching logic.

Provides:
- ``RORClient`` / ``CachingRORClient`` — HTTP client for the ROR API
- ``resolve_funders`` — match funder metadata to database organizations
- ``FunderMatch``, ``ResolvedFunder`` — domain types for the resolution pipeline
"""

from ._resolver import FunderMatch as FunderMatch
from ._resolver import ResolvedFunder as ResolvedFunder
from ._resolver import resolve_funders as resolve_funders
from .ror_client import CachingRORClient as CachingRORClient
from .ror_client import RORClient as RORClient
from .ror_client import RORClientError as RORClientError
from .ror_client import RORRecord as RORRecord

__all__ = [
    "CachingRORClient",
    "FunderMatch",
    "RORClient",
    "RORClientError",
    "RORRecord",
    "ResolvedFunder",
    "resolve_funders",
]
