import datetime
from typing import Literal

from django.db.models import Prefetch, QuerySet
from django.urls import reverse

from coda.apps.fundingrequests.mappers._domain import FundingRequestDomainMapper
from coda.apps.fundingrequests.models import ExternalFunding as ExternalFundingModel
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.queries.mappers import AuthorDetailMapper, PublicationDetailMapper
from coda.apps.fundingrequests.queries.models import (
    EstimatedCostDetail,
    ExternalFundingDetail,
    FundingRequestDetail,
    PublicationPaymentDetail,
    ReviewDetail,
)
from coda.apps.publications.mappers._domain import PublicationDomainMapper
from coda.apps.publications.models import Publication as PublicationModel
from coda.domain.author import InstitutionId
from coda.domain.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.money import Currency, Money


class FundingRequestDetailMapper:
    @staticmethod
    def prefetch(
        qs: QuerySet[FundingRequestModel], prefix: str = ""
    ) -> QuerySet[FundingRequestModel]:
        qs = qs.select_related("extra_contact", "review")
        qs = PublicationDomainMapper.prefetch(qs, prefix="publication")
        return qs.prefetch_related(
            Prefetch(
                "external_funding",
                queryset=ExternalFundingModel.objects.select_related("organization"),
            ),
            "labels",
        )

    @staticmethod
    def map(
        model: FundingRequestModel,
        affiliation_names: dict[InstitutionId, str],
        payment_details: PublicationPaymentDetail,
    ) -> FundingRequestDetail:
        fr = FundingRequestDomainMapper.map(model)
        pub_model = model.publication
        entity_type, entity_name, identifier_name, identifier = _resolve_publishing_entity(
            pub_model
        )

        author_details = AuthorDetailMapper.map_all(
            fr.publication.relevant_authors, affiliation_names
        )

        publication_detail = PublicationDetailMapper.map(
            pub=fr.publication,
            author_details=author_details,
            edit_url=_get_edit_url(pub_model, model.pk),
            request_remarks=model.request_remarks,
            payment_details=payment_details,
            publishing_entity_type=entity_type,
            publishing_entity_name=entity_name,
            publishing_entity_identifier_name=identifier_name,
            publishing_entity_identifier=identifier,
        )

        external_funding = [
            ExternalFundingDetail(
                organization=ef.organization.name,
                project_id=ef.project_id,
                project_name=ef.project_name,
            )
            for ef in model.external_funding.all()
        ]

        review_model = getattr(model, "review", None)
        decided_amount = _resolve_decided_amount(model)
        review = ReviewDetail(
            value=review_model.review_result if review_model else "open",
            remarks=review_model.remarks if review_model else "",
            funding_amount=decided_amount,
        )

        estimated_cost = EstimatedCostDetail(
            amount=Money(model.estimated_cost, Currency.from_code(model.estimated_cost_currency)),
            method=PaymentMethod(model.payment_method),
        )

        return FundingRequestDetail(
            id=model.pk,
            request_id=model.request_id,
            request_date=_parse_request_date(model.request_id),
            review=review,
            review_remarks=review_model.remarks if review_model else "",
            funding_amount=decided_amount,
            estimated_cost=estimated_cost,
            external_costsplitting=model.external_costsplitting or False,
            publication=publication_detail,
            external_funding=external_funding,
            updated_at=model.updated_at.date(),
            labels=model.labels.all(),
            edit_submitter_url=reverse("fundingrequests:update_submitter", kwargs={"pk": model.pk}),
            edit_funding_url=reverse("fundingrequests:update_funding", kwargs={"pk": model.pk}),
            contact=model.extra_contact,
        )


def _resolve_publishing_entity(
    pub_model: PublicationModel,
) -> tuple[Literal["Journal", "Publisher"], str, str, str]:
    if pub_model.article_journal is not None:
        journal = pub_model.article_journal
        publisher_name = journal.publisher.name if journal.publisher else ""
        name = f"{journal.title}, {publisher_name}" if publisher_name else journal.title
        return ("Journal", name, "EISSN", journal.eissn or "")
    else:
        publisher = pub_model.monograph_publisher
        assert publisher is not None
        return ("Publisher", publisher.name, "", "")


def _get_edit_url(pub_model: PublicationModel, fr_id: int) -> str:
    if pub_model.article_journal is not None:
        return reverse("fundingrequests:update_publication", kwargs={"pk": fr_id})
    return reverse("fundingrequests:update_monograph_meta", kwargs={"pk": fr_id})


def _resolve_decided_amount(model: FundingRequestModel) -> object:
    review_model = getattr(model, "review", None)
    if review_model and review_model.decided_funding_amount:
        return Money(
            review_model.decided_funding_amount,
            Currency.from_code(review_model.decided_funding_currency or "EUR"),
        )
    return Money(model.estimated_cost, Currency.from_code(model.estimated_cost_currency))


def _parse_request_date(request_id: str) -> datetime.date:
    return PublicFundingRequestId.from_str(request_id).date()
