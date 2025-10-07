"""Mapper functions for Review domain objects."""

from coda.apps.fundingrequests import models as fundingrequest_models
from coda.domain.fundingrequest import FundingRequestId, Review
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money


def as_domain_object(
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


def create_django_model(review: Review) -> fundingrequest_models.FundingRequestReview:
    """Create new Django model instance from domain Review."""
    return fundingrequest_models.FundingRequestReview(
        review_result=review.result.value if review.result else "unknown",
        decided_funding_amount=review.decided_funding.amount if review.decided_funding else 0,
        decided_funding_currency=review.decided_funding.currency.code
        if review.decided_funding
        else "EUR",
        remarks=review.remarks,
    )


def update_django_model(
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


def as_django_model(review: Review) -> fundingrequest_models.FundingRequestReview:
    """Convert domain Review to Django model instance."""
    return create_django_model(review)
