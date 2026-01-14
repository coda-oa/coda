"""FundingRequest import service - main orchestration.

This module coordinates the import process:
1. Loading and validating JSON
2. Processing validated requests (parsing, entity creation)
3. Persisting to database
4. Attaching labels and reviews
"""

from typing import BinaryIO, TextIO
from collections.abc import Iterable

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.services import labels as label_services
from coda.apps.fundingrequests.services.fundingrequests import bulk_create_fundingrequests
from coda.checks.nullcheckfactory import NullCheckFactory
from coda.contexts.fundingrequest.dto.import_dtos import FundingRequestImportListDto
from coda.contexts.fundingrequest.services.import_service.types import FundingRequestImportReport
from coda.domain.fundingrequest import FundingRequestId, Review
from coda.domain.money import Currency, Money

from ._entity_creation import build_entity_lookups
from ._parsing import parse_requests


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
    """Process validated requests: parse, create, attach labels/reviews."""
    errors: dict[str, list[str]] = {}

    lookups = build_entity_lookups(import_data)
    creation_dtos = parse_requests(import_data, lookups, errors)

    ids, create_errors = bulk_create_fundingrequests(creation_dtos, checkfactory=NullCheckFactory())
    for error in create_errors:
        errors.setdefault(error.request_key, []).append(error.reason)

    _attach_labels(import_data, ids, errors)
    _save_reviews(import_data, ids, errors)

    return len(list(ids)), errors


def _attach_labels(
    import_data: FundingRequestImportListDto,
    ids: Iterable[FundingRequestId],
    errors: dict[str, list[str]],
) -> None:
    """Attach labels to created funding requests."""
    all_label_names = set()
    for request in import_data.requests:
        all_label_names.update(request.labels)

    available_labels = label_services.label_bulk_get_or_create(all_label_names)
    for fundingrequest_id, request in zip(ids, import_data.requests):
        if request.labels:
            try:
                labels_for_request = [
                    available_labels[name] for name in request.labels if name in available_labels
                ]
                label_services.label_attach_bulk_by_id(fundingrequest_id, labels_for_request)
            except Exception as e:
                error_key = request.legacy_request_id or request.publication.title
                errors.setdefault(error_key, []).append(f"Failed to process labels: {str(e)}")


def _save_reviews(
    import_data: FundingRequestImportListDto,
    ids: Iterable[FundingRequestId],
    errors: dict[str, list[str]],
) -> None:
    """Save reviews for created funding requests."""

    for fundingrequest_id, request in zip(ids, import_data.requests):
        try:
            review = Review(
                fundingrequest=fundingrequest_id,
                result=request.review.result,
                remarks=request.review.remarks,
                decided_funding=Money(
                    amount=request.review.funding.amount,
                    currency=Currency.from_code(request.review.funding.currency),
                ),
            )
            repository.save_review(review)
        except Exception as e:
            error_key = request.legacy_request_id or request.publication.title
            errors.setdefault(error_key, []).append(f"Failed to save review: {str(e)}")
