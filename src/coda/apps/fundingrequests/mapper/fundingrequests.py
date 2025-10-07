"""Mapper functions for FundingRequest domain objects."""

from collections.abc import Iterable
from typing import Any

from coda.apps.fundingrequests import models as fundingrequest_models
from coda.apps.publications.repositories import publication_repository
from coda.domain.fundingrequest import (
    AnyFundingRequest,
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    NoContact,
    Payment,
    PaymentMethod,
    Review,
)
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.publication import PublicationId
from coda.domain.string import NonEmptyStr

from . import contacts, external_funding, reviews


def _map_payment_to_model_fields(payment: Payment) -> dict[str, Any]:
    """Extract payment fields for model creation/update."""
    return {
        "estimated_cost": payment.amount.amount,
        "estimated_cost_currency": payment.amount.currency.code,
        "payment_method": payment.method.value,
    }


def _map_request_id_to_model_fields(request_id: PublicFundingRequestId) -> dict[str, Any]:
    """Extract request ID fields for model creation/update."""
    return {
        "request_id": str(request_id),
        "request_date": request_id.date(),
        "request_number": request_id.id_without_checksum(),
    }


def as_domain_object(model: fundingrequest_models.FundingRequest) -> AnyFundingRequest:
    """Convert FundingRequestModel to domain object."""
    fr_id = FundingRequestId(model.pk)
    review = _get_review(getattr(model, "review", None), fr_id)

    fr = FundingRequest(
        id=fr_id,
        request_id=PublicFundingRequestId.from_str(model.request_id),
        publication=publication_repository.get_by_id(PublicationId(model.publication.id)),
        extra_contact=(
            FilledContact(NonEmptyStr(model.extra_contact.name), model.extra_contact.email)
            if model.extra_contact
            else NoContact
        ),
        estimated_cost=Payment(
            amount=Money(model.estimated_cost, Currency.from_code(model.estimated_cost_currency)),
            method=PaymentMethod(model.payment_method),
        ),
        external_funding=[
            ExternalFunding(
                organization=FundingOrganizationId(ef.organization_id),
                project_id=NonEmptyStr(ef.project_id),
                project_name=ef.project_name,
            )
            for ef in getattr(model, "external_funding").all()
        ],
        request_remarks=model.request_remarks,
        review=review,
        legacy_request_id=model.legacy_request_id,
    )

    return fr


def _get_review(
    model: fundingrequest_models.FundingRequestReview | None, fr_id: FundingRequestId
) -> Review:
    """Convert FundingRequestReview model to domain Review."""
    if not model:
        return Review(fr_id)

    review_result = ReviewResult.of(model.review_result)
    return Review(
        fr_id,
        decided_funding=Money(
            model.decided_funding_amount or 0,
            Currency.from_code(model.decided_funding_currency or "EUR"),
        ),
        remarks=model.remarks,
        result=review_result,
    )


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

    if fundingrequest.id is None:
        model = fundingrequest_models.FundingRequest(**fields)
    else:
        model = fundingrequest_models.FundingRequest.objects.get(pk=fundingrequest.id)
        for field, value in fields.items():
            setattr(model, field, value)

    setattr(model, "publication_id", fundingrequest.publication.id)
    return model


def update_payment_fields(payment: Payment, model: fundingrequest_models.FundingRequest) -> None:
    """Update payment-related fields on model from domain Payment object."""
    payment_fields = _map_payment_to_model_fields(payment)
    for field, value in payment_fields.items():
        setattr(model, field, value)


def synchronize_relationships(
    fundingrequest: AnyFundingRequest, model: fundingrequest_models.FundingRequest
) -> None:
    """Synchronize relationships between domain object and Django model."""
    model.review = reviews.as_django_model(fundingrequest._review)
    model.review.save()

    if not fundingrequest.extra_contact:
        model.extra_contact
    contacts.synchronize_contact_relationship(model, fundingrequest.extra_contact)

    if not model.pk:
        model.save()

    if model.pk:
        external_funding.synchronize_external_funding_relationship(
            model, fundingrequest.external_funding
        )


def create_bulk_models(
    fundingrequests: Iterable[AnyFundingRequest],
    publication_ids: Iterable[PublicationId],
    reviews: Iterable[fundingrequest_models.FundingRequestReview],
) -> list[fundingrequest_models.FundingRequest]:
    """Create FundingRequestModel instances for bulk creation."""
    return [
        fundingrequest_models.FundingRequest(
            publication_id=pid,
            request_remarks=fundingrequest.request_remarks,
            review=review,
            legacy_request_id=fundingrequest.legacy_request_id,
            **_map_request_id_to_model_fields(fundingrequest.request_id),
            **_map_payment_to_model_fields(fundingrequest.estimated_cost),
        )
        for fundingrequest, pid, review in zip(fundingrequests, publication_ids, reviews)
    ]
