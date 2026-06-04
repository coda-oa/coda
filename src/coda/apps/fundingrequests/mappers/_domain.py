from django.db.models import QuerySet

from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import FundingRequestReview as FundingRequestReviewModel
from coda.apps.publications.mappers._domain import PublicationDomainMapper
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
from coda.domain.string import NonEmptyStr


class FundingRequestDomainMapper:
    @staticmethod
    def prefetch(
        qs: QuerySet[FundingRequestModel], prefix: str = ""
    ) -> QuerySet[FundingRequestModel]:
        qs = qs.select_related("extra_contact", "review")
        qs = PublicationDomainMapper.prefetch(qs, prefix="publication")
        qs = qs.prefetch_related("external_funding")
        return qs

    @staticmethod
    def map(model: FundingRequestModel) -> AnyFundingRequest:
        fr_id = FundingRequestId(model.pk)
        review = _map_review(getattr(model, "review", None), fr_id)

        return FundingRequest(
            id=fr_id,
            request_id=PublicFundingRequestId.from_str(model.request_id),
            publication=PublicationDomainMapper.map(model.publication),
            extra_contact=(
                FilledContact(NonEmptyStr(model.extra_contact.name), model.extra_contact.email)
                if model.extra_contact
                else NoContact
            ),
            estimated_cost=Payment(
                amount=Money(
                    model.estimated_cost, Currency.from_code(model.estimated_cost_currency)
                ),
                method=PaymentMethod(model.payment_method),
                external_costsplitting=model.external_costsplitting,
            ),
            external_funding=[
                ExternalFunding(
                    organization=FundingOrganizationId(ef.organization_id),
                    project_id=ef.project_id,
                    project_name=ef.project_name,
                )
                for ef in model.external_funding.all()
            ],
            request_remarks=model.request_remarks,
            review=review,
            legacy_request_id=model.legacy_request_id,
        )


def _map_review(model: FundingRequestReviewModel | None, fr_id: FundingRequestId) -> Review:
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
