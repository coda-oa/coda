"""FundingRequest import service - main orchestration.

This module coordinates the import process:
1. Loading and validating JSON
2. Processing validated requests (parsing, entity creation)
3. Persisting to database
4. Attaching labels and reviews
"""

from typing import BinaryIO, TextIO
from collections.abc import Iterable

try:
    from silk.profiling.profiler import silk_profile
except (ImportError, RuntimeError):
    # Silk not available in tests or not configured
    def silk_profile(*args, **kwargs):  # type: ignore
        def decorator(func):  # type: ignore
            return func

        return decorator


from coda.apps.fundingrequests.models import Label
from coda.contexts.fundingrequest.services import labels as label_services
from coda.contexts.fundingrequest.services.fundingrequests import bulk_create_fundingrequests
from coda.checks.nullcheckfactory import NullCheckFactory
from coda.contexts.fundingrequest.dto.import_dtos import FundingRequestImportListDto
from coda.contexts.fundingrequest.services.import_service.types import FundingRequestImportReport
from coda.domain.contract import Contract, ContractId
from coda.domain.fundingrequest import FundingRequestId

from ._entity_creation import build_entity_lookups
from ._parsing import parse_requests


@silk_profile(name="Import funding requests")  # type: ignore
def import_fundingrequests(json: TextIO | BinaryIO) -> FundingRequestImportReport:
    """Import funding requests from JSON stream.

    Args:
        json: JSON input containing funding request data

    Returns:
        Import report with counts and any errors
    """
    data = _load_json(json)
    processed_count, processing_errors = _process_requests(data)

    return FundingRequestImportReport(
        valid_requests=processed_count,
        invalid_requests=len(processing_errors),
        errors=processing_errors,
    )


def _load_json(json: TextIO | BinaryIO) -> FundingRequestImportListDto:
    """Load and validate JSON structure."""
    return FundingRequestImportListDto.model_validate_json(json.read())


def _process_requests(
    import_data: FundingRequestImportListDto,
) -> tuple[int, dict[str, list[str]]]:
    """Process validated requests: parse, create, attach labels.

    Builds entity lookups once, then uses in-memory contract lookup
    to avoid N+1 queries during funding request creation.
    """
    errors: dict[str, list[str]] = {}

    # Build all entity lookups once (keyed by name)
    lookups = build_entity_lookups(import_data)

    # Build contract ID lookup for efficient ID-based retrieval
    # (lookups.contracts is keyed by name, but we need lookup by ID)
    contract_id_lookup: dict[ContractId, Contract] = {
        contract.id: contract for contract in lookups.contracts.values() if contract.id is not None
    }

    # Create contract fetcher that uses in-memory lookup instead of DB
    def get_contract_from_lookup(contract_id: ContractId) -> Contract:
        """Fetch contract from in-memory ID-indexed lookup.

        Args:
            contract_id: ID of contract to fetch

        Returns:
            Contract domain object

        Raises:
            KeyError: If contract_id not found in lookup
        """
        return contract_id_lookup[contract_id]

    # Parse import DTOs into creation DTOs using lookups
    creation_dtos = parse_requests(import_data, lookups, errors)

    # Bulk create funding requests, passing the optimized contract fetcher
    ids, create_errors = bulk_create_fundingrequests(
        creation_dtos, checkfactory=NullCheckFactory(), get_contract_by_id=get_contract_from_lookup
    )
    for error in create_errors:
        errors.setdefault(error.request_key, []).append(error.reason)

    _attach_labels(import_data, ids, errors)
    # Reviews now created with correct values during bulk_create, no update needed!

    return len(list(ids)), errors


def _attach_labels(
    import_data: FundingRequestImportListDto,
    ids: Iterable[FundingRequestId],
    errors: dict[str, list[str]],
) -> None:
    """Attach labels to created funding requests."""
    # Collect all unique label names using set comprehension
    all_label_names = {
        label_name for request in import_data.requests for label_name in request.labels
    }

    available_labels = label_services.label_bulk_get_or_create(all_label_names)

    # Build mapping: funding_request_id -> [labels]
    request_labels: dict[FundingRequestId, list[Label]] = {}
    for fundingrequest_id, request in zip(ids, import_data.requests):
        if not request.labels:
            continue  # Early return - skip requests without labels

        try:
            labels_for_request = [
                available_labels[name] for name in request.labels if name in available_labels
            ]
            if labels_for_request:
                request_labels[fundingrequest_id] = labels_for_request
        except Exception as e:
            error_key = request.legacy_request_id or request.publication.title
            errors.setdefault(error_key, []).append(f"Failed to process labels: {str(e)}")

    # Single bulk operation for all label attachments
    if request_labels:
        label_services.label_attach_bulk_many(request_labels)
