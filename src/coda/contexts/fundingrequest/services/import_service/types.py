"""Shared types for the import service."""

from dataclasses import dataclass
from typing import NamedTuple

from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.institutions.models import Institution
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.domain.contract import Contract
from coda.domain.vocabulary import Vocabulary


@dataclass(frozen=True)
class FundingRequestImportReport:
    """Report of import operation results."""

    valid_requests: int
    invalid_requests: int
    errors: dict[str, list[str]]


@dataclass(frozen=True)
class FundingRequestProcessingError:
    """Error that occurred during request processing."""

    request_key: str  # legacy_id or title
    errors: list[str]


class ImportLookups(NamedTuple):
    """Cached lookups for entity creation."""

    funding_organizations: dict[str, FundingOrganization]
    contracts: dict[str, Contract]
    institutions: dict[str, Institution]
    vocabularies: dict[str, Vocabulary]
    publishers: dict[str, Publisher]
    journals: dict[str, Journal]
