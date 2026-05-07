"""Mapper functions for FundingRequest domain objects."""

from collections.abc import Iterable
from typing import Any

from coda.apps.fundingrequests import models as fundingrequest_models
from coda.domain.fundingrequest import (
    AnyFundingRequest,
    ExternalFunding,
    FundingRequestContact,
    Payment,
    Review,
)
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.publication import PublicationId


def as_django_model(fundingrequest: AnyFundingRequest) -> fundingrequest_models.FundingRequest:
    """Convert domain FundingRequest to Django model instance.

    Automatically detects if this should create a new model or update existing:
    - If fundingrequest.id is None: Creates new model instance
    - If fundingrequest.id exists: Fetches existing model from DB and updates it
    """
    fields = {
        "request_remarks": fundingrequest.request_remarks,
        "legacy_request_id": fundingrequest.legacy_request_id,
        **_map_request_id_to_model_fields(fundingrequest.request_id),
        **_map_payment_to_model_fields(fundingrequest.estimated_cost),
    }

    if not fundingrequest.id.resolved:
        model = fundingrequest_models.FundingRequest(**fields)
    else:
        model = fundingrequest_models.FundingRequest.objects.get(pk=fundingrequest.id.pk)
        for field, value in fields.items():
            setattr(model, field, value)

    setattr(model, "publication_id", fundingrequest.publication.id.pk)
    return model


def synchronize_relationships(
    fundingrequest: AnyFundingRequest, model: fundingrequest_models.FundingRequest
) -> None:
    """Synchronize relationships between domain object and Django model."""
    # Handle review - always create new review model
    model.review = _create_review_model(fundingrequest._review)
    model.review.save()

    # Handle contact
    _synchronize_contact(model, fundingrequest.extra_contact)

    # Save model to ensure it has a primary key
    if not model.pk:
        model.save()

    # Handle external funding (needs model to have pk)
    if model.pk:
        _synchronize_external_funding(model, fundingrequest.external_funding)


def update_payment_fields(payment: Payment, model: fundingrequest_models.FundingRequest) -> None:
    """Update payment-related fields on model from domain Payment object."""
    payment_fields = _map_payment_to_model_fields(payment)
    for field, value in payment_fields.items():
        setattr(model, field, value)


def create_bulk_models(
    fundingrequests: Iterable[AnyFundingRequest],
    publication_ids: Iterable[PublicationId],
    reviews: Iterable[fundingrequest_models.FundingRequestReview],
) -> list[fundingrequest_models.FundingRequest]:
    """Create FundingRequestModel instances for bulk creation."""
    return [
        fundingrequest_models.FundingRequest(
            publication_id=pid.pk,
            request_remarks=fundingrequest.request_remarks,
            review=review,
            legacy_request_id=fundingrequest.legacy_request_id,
            **_map_request_id_to_model_fields(fundingrequest.request_id),
            **_map_payment_to_model_fields(fundingrequest.estimated_cost),
        )
        for fundingrequest, pid, review in zip(fundingrequests, publication_ids, reviews)
    ]


# Internal helper functions


def _map_payment_to_model_fields(payment: Payment) -> dict[str, Any]:
    """Extract payment fields for model creation/update."""
    return {
        "estimated_cost": payment.amount.amount,
        "estimated_cost_currency": payment.amount.currency.code,
        "payment_method": payment.method.value,
        "external_costsplitting": payment.external_costsplitting,
    }


def _map_request_id_to_model_fields(request_id: PublicFundingRequestId) -> dict[str, Any]:
    """Extract request ID fields for model creation/update."""
    return {
        "request_id": str(request_id),
        "request_date": request_id.date(),
        "request_number": request_id.id_without_checksum(),
    }


def _create_review_model(review: Review) -> fundingrequest_models.FundingRequestReview:
    """Create new Django model instance from domain Review."""
    return fundingrequest_models.FundingRequestReview(
        review_result=review.result.value if review.result else "unknown",
        decided_funding_amount=review.decided_funding.amount if review.decided_funding else 0,
        decided_funding_currency=(
            review.decided_funding.currency.code if review.decided_funding else "EUR"
        ),
        remarks=review.remarks,
    )


def update_review_model(
    review: Review, review_model: fundingrequest_models.FundingRequestReview
) -> None:
    """Update existing Django model with domain Review data."""
    review_model.review_result = review.result.value if review.result else "unknown"
    review_model.decided_funding_amount = (
        review.decided_funding.amount if review.decided_funding else 0
    )
    review_model.decided_funding_currency = (
        review.decided_funding.currency.code if review.decided_funding else "EUR"
    )
    review_model.remarks = review.remarks


def _create_contact_model(
    contact: FundingRequestContact,
) -> fundingrequest_models.FundingRequestContact:
    """Create a new FundingRequestContact model from domain object."""
    contact_model = fundingrequest_models.FundingRequestContact()
    contact_model.name = contact.name
    contact_model.email = contact.email
    return contact_model


def _synchronize_contact(
    fr_model: fundingrequest_models.FundingRequest, contact: FundingRequestContact
) -> None:
    """Synchronize contact relationship with create/update/delete logic."""
    if not contact and not fr_model.extra_contact:
        return

    if not contact and fr_model.extra_contact:
        fr_model.extra_contact.delete()
        fr_model.extra_contact = None
        return

    extra_contact = _create_contact_model(contact)
    if fr_model.extra_contact:
        extra_contact.pk = fr_model.extra_contact.pk

    fr_model.extra_contact = extra_contact
    fr_model.extra_contact.save()


def _create_external_funding_models(
    fr_id: int, funding: Iterable[ExternalFunding]
) -> list[fundingrequest_models.ExternalFunding]:
    """Create ExternalFunding model instances for given funding request."""
    return [
        fundingrequest_models.ExternalFunding(
            funding_request_id=fr_id,
            organization_id=ef.organization.pk,
            project_id=ef.project_id,
            project_name=ef.project_name,
        )
        for ef in funding
    ]


def _synchronize_external_funding(
    fr: fundingrequest_models.FundingRequest, funding: Iterable[ExternalFunding]
) -> None:
    """Synchronize external funding relationship by replacing all records."""
    fr.external_funding.all().delete()

    if funding:
        external_funding_models = _create_external_funding_models(fr.pk, funding)
        fundingrequest_models.ExternalFunding.objects.bulk_create(external_funding_models)


# Bulk creation helper functions


def create_bulk_external_funding_models(
    fundingrequests: Iterable[AnyFundingRequest],
    created_frs: Iterable[fundingrequest_models.FundingRequest],
) -> list[fundingrequest_models.ExternalFunding]:
    """Create ExternalFunding model instances for bulk creation."""
    return [
        fundingrequest_models.ExternalFunding(
            funding_request_id=fr.pk,
            organization_id=ef.organization.pk,
            project_id=ef.project_id,
            project_name=ef.project_name,
        )
        for fundingrequest, fr in zip(fundingrequests, created_frs)
        for ef in fundingrequest.external_funding
    ]


def create_bulk_contact_models_and_map(
    fundingrequests: Iterable[AnyFundingRequest],
    created_frs: Iterable[fundingrequest_models.FundingRequest],
) -> tuple[
    list[fundingrequest_models.FundingRequestContact],
    dict[int, fundingrequest_models.FundingRequestContact],
]:
    """Create FundingRequestContact model instances for bulk creation and return mapping."""
    contact_map: dict[int, fundingrequest_models.FundingRequestContact] = {}

    for fundingrequest, fr in zip(fundingrequests, created_frs):
        contact = fundingrequest.extra_contact
        if contact:
            contact_obj = _create_contact_model(contact)
            contact_map[fr.pk] = contact_obj

    contact_objs = list(contact_map.values())
    return contact_objs, contact_map
