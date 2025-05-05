from collections.abc import Iterable, Sequence
from typing import Any, cast

from django.db import transaction
from django.db.models import Q
from typing_extensions import TypeIs

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.fundingrequests.models import ExternalFunding as ExternalFundingModel
from coda.apps.fundingrequests.models import FundingOrganization, FundingRequestReview
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import FundingRequestContact as FundingRequestContactModel
from coda.apps.publications.repositories import publication_repository
from coda.domain.date import DateRange
from coda.domain.fundingrequest import (
    AnyFundingRequest,
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestContact,
    FundingRequestId,
    NoContact,
    Payment,
    PaymentMethod,
    Review,
    TPublication,
)
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.publication import Monograph, OpenAccessType, Publication, PublicationId
from coda.domain.publication.payment import (
    InvoiceReceived,
    PublicationCoveredByContract,
    PublicationPaid,
    PublicationPaymentStatus,
    PublicationUnpaid,
)
from coda.domain.string import NonEmptyStr


@transaction.atomic
def create(fundingrequest: AnyFundingRequest) -> FundingRequestId:
    if fundingrequest.id:
        raise FundingRequestAlreadyExists(fundingrequest.id)

    pid = publication_repository.create(fundingrequest.publication)
    fr = FundingRequestModel()
    fr.review = FundingRequestReview.objects.create()
    _save_review(fundingrequest._review, fr.review)

    return _save(fundingrequest, fr, pid)


def _save(
    fundingrequest: AnyFundingRequest, fr: FundingRequestModel, pid: PublicationId
) -> FundingRequestId:
    fr.publication_id = pid
    fr.request_id = str(fundingrequest.request_id)
    fr.request_remarks = fundingrequest.request_remarks

    _save_contact(fundingrequest.extra_contact, fr)
    _save_funding(fr, fundingrequest.estimated_cost, fundingrequest.external_funding)

    fr.save()
    return FundingRequestId(fr.id)


@transaction.atomic
def update(fundingrequest: AnyFundingRequest) -> None:
    if not fundingrequest.id:
        raise UnsavedFundingRequest(fundingrequest)

    pid = cast(PublicationId, fundingrequest.publication.id)
    publication_repository.update(fundingrequest.publication)
    fr = FundingRequestModel.objects.get(pk=fundingrequest.id)
    _save(fundingrequest, fr, pid)


@transaction.atomic
def create_many(fundingrequests: Iterable[AnyFundingRequest]) -> Iterable[FundingRequestId]:
    fundingrequests = list(fundingrequests)
    reviews = FundingRequestReview.objects.bulk_create(
        [FundingRequestReview() for _ in fundingrequests]
    )
    publication_ids = [
        publication_repository.create(fundingrequest.publication)
        for fundingrequest in fundingrequests
    ]
    fr_models = [
        FundingRequestModel(
            request_id=str(fundingrequest.request_id),
            publication_id=pid,
            request_remarks=fundingrequest.request_remarks,
            estimated_cost=fundingrequest.estimated_cost.amount.amount,
            estimated_cost_currency=fundingrequest.estimated_cost.amount.currency.code,
            payment_method=fundingrequest.estimated_cost.method.value,
            review=review,
        )
        for fundingrequest, pid, review in zip(fundingrequests, publication_ids, reviews)
    ]
    created_frs = FundingRequestModel.objects.bulk_create(fr_models)
    external_funding_objs = []
    contact_objs = []
    contact_map = {}  # Map FundingRequestModel.id to FundingRequestContactModel

    for fundingrequest, fr in zip(fundingrequests, created_frs):
        for ef in fundingrequest.external_funding:
            external_funding_objs.append(
                ExternalFundingModel(
                    funding_request_id=fr.id,
                    organization_id=ef.organization,
                    project_id=ef.project_id,
                    project_name=ef.project_name,
                )
            )
        contact = fundingrequest.extra_contact
        if contact:
            contact_obj = FundingRequestContactModel(
                funding_request=fr,
                name=contact.name,
                email=contact.email,
            )  # type: ignore[misc]
            contact_objs.append(contact_obj)
            contact_map[fr.id] = contact_obj

    if external_funding_objs:
        ExternalFundingModel.objects.bulk_create(external_funding_objs)

    if contact_objs:
        FundingRequestContactModel.objects.bulk_create(contact_objs)
        # Now update the extra_contact field on each FundingRequestModel
        for fr in created_frs:
            model_contact = contact_map.get(fr.id)
            if model_contact:
                fr.extra_contact = model_contact
                fr.save(update_fields=["extra_contact"])

    return tuple(FundingRequestId(fr.id) for fr in created_frs)


class FundingRequestAlreadyExists(ValueError):
    def __init__(self, fundingrequest_id: FundingRequestId) -> None:
        super().__init__(f"Funding request with id {fundingrequest_id} already exists")
        self.fundingrequest_id = fundingrequest_id


class UnsavedFundingRequest(ValueError):
    def __init__(self, fundingrequest: AnyFundingRequest) -> None:
        super().__init__(f"Funding request {fundingrequest} is not saved")
        self.fundingrequest = fundingrequest


@transaction.atomic
def save_review(review: Review) -> None:
    review_model = FundingRequestReview.objects.filter(fundingrequest=review.fundingrequest).get()
    _save_review(review, review_model)


def _save_review(review: Review, review_model: FundingRequestReview) -> None:
    review_model.review_result = review.result.value
    review_model.decided_funding_amount = review.decided_funding.amount
    review_model.decided_funding_currency = review.decided_funding.currency.code
    review_model.remarks = review.remarks
    review_model.save()


@transaction.atomic
def save_contact(id: FundingRequestId, contact: FundingRequestContact) -> None:
    fr = FundingRequestModel.objects.get(pk=id)
    _save_contact(contact, fr)


@transaction.atomic
def save_funding(
    id: FundingRequestId, payment: Payment, funding: Iterable[ExternalFunding]
) -> None:
    fr = FundingRequestModel.objects.get(pk=id)
    _save_funding(fr, payment, funding)


def _save_funding(
    fr: FundingRequestModel, payment: Payment, funding: Iterable[ExternalFunding]
) -> None:
    fr.estimated_cost = payment.amount.amount
    fr.estimated_cost_currency = payment.amount.currency.code
    fr.payment_method = payment.method.value
    fr.save()
    fr.external_funding.all().delete()
    _save_external_funding(fr, funding)


def _save_external_funding(fr: FundingRequestModel, funding: Iterable[ExternalFunding]) -> None:
    ExternalFundingModel.objects.bulk_create(
        ExternalFundingModel(
            funding_request_id=fr.id,
            organization_id=ef.organization,
            project_id=ef.project_id,
            project_name=ef.project_name,
        )
        for ef in funding
    )


def request_id_exists(request_id: PublicFundingRequestId) -> bool:
    return FundingRequestModel.objects.filter(request_id=str(request_id)).exists()


def first() -> AnyFundingRequest | None:
    model = FundingRequestModel.objects.first()
    if model:
        return as_domain_object(model)
    else:
        return None


def get_by_id(id: FundingRequestId) -> AnyFundingRequest:
    model = FundingRequestModel.objects.get(pk=id)
    return as_domain_object(model)


def all() -> Sequence[AnyFundingRequest]:
    return DomainQuerySet(
        FundingRequestModel.objects.all()
        .select_related(
            "review",
            "publication__article_journal",
            "publication__monograph_publisher",
        )
        .prefetch_related(
            "labels",
            "publication__relevant_authors",
        ),
        as_domain_object,
    )


def get_article_request(id: FundingRequestId) -> FundingRequest[Publication]:
    fr = get_by_id(id)
    if not _is_publication_type(fr, Publication):
        raise ValueError(f"Funding request with id {id} is not an article request")

    return fr


def get_monograph_request(id: FundingRequestId) -> FundingRequest[Monograph]:
    fr = get_by_id(id)
    if not _is_publication_type(fr, Monograph):
        raise ValueError(f"Funding request with id {id} is not a monograph request")

    return fr


def _is_publication_type(
    fr: Any, publication_type: type[TPublication]
) -> TypeIs[FundingRequest[TPublication]]:
    return isinstance(fr, FundingRequest) and isinstance(fr.publication, publication_type)


def as_domain_object(model: FundingRequestModel) -> AnyFundingRequest:
    fr_id = FundingRequestId(model.id)
    review = _get_review(getattr(model, "review", None), fr_id)

    fr = FundingRequest(
        id=fr_id,
        request_id=PublicFundingRequestId.from_str(model.request_id),
        publication=publication_repository.get_by_id(PublicationId(model.publication_id)),
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
            for ef in model.external_funding.all()
        ],
        request_remarks=model.request_remarks,
        review=review,
    )

    return fr


def get_review(id: FundingRequestId) -> Review:
    model = FundingRequestReview.objects.filter(fundingrequest=id).first()
    return _get_review(model, id)


def _get_review(model: FundingRequestReview | None, fr_id: FundingRequestId) -> Review:
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


def _save_contact(contact: FundingRequestContact, fr: FundingRequestModel) -> None:
    if contact:
        extra_contact = fr.extra_contact
        if not extra_contact:
            extra_contact = FundingRequestContactModel()
            extra_contact.funding_request = fr

        extra_contact.name = contact.name
        extra_contact.email = contact.email
        extra_contact.save()
    elif fr.extra_contact:
        fr.extra_contact.delete()
        fr.extra_contact = None


def search(
    *,
    generic_search: str | None = None,
    title: str | None = None,
    author: str | None = None,
    publisher: str | None = None,
    processing_states: list[ReviewResult] | None = None,
    open_access_types: list[OpenAccessType] | None = None,
    date_range: DateRange | None = None,
    payment_statuses: list[type[PublicationPaymentStatus]] | None = None,
    labels: Iterable[int] | None = None,
    exclude_labels: Iterable[int] | None = None,
) -> Iterable[FundingRequestModel]:
    query = Q()

    if generic_search:
        query = query & (
            Q(publication__title__icontains=generic_search)
            | Q(publication__relevant_authors__name__icontains=generic_search)
            | Q(publication__article_journal__title__icontains=generic_search)
            | Q(publication__article_journal__publisher__name__icontains=generic_search)
            | Q(publication__monograph_publisher__name__icontains=generic_search)
            | Q(request_id__icontains=generic_search)
        )

    if title:
        query = query & Q(publication__title__icontains=title)

    if author:
        query = query & Q(publication__relevant_authors__name__icontains=author)

    if publisher:
        query = query & Q(publication__article_journal__publisher__name__icontains=publisher)

    if processing_states:
        review_states = [s.value.lower() for s in processing_states]
        query = query & Q(review__review_result__in=review_states)

    if open_access_types:
        oa_types = [t.name for t in open_access_types]
        query = query & Q(publication__open_access_type__in=oa_types)

    if labels:
        query = query & Q(labels__in=labels)

    if exclude_labels:
        query = query & ~Q(labels__in=exclude_labels)

    if date_range and not date_range.is_unbounded():
        query = query & Q(created_at__gte=date_range.start, created_at__lte=date_range.end)

    if payment_statuses:
        payment_query = Q()

        if PublicationCoveredByContract in payment_statuses:
            payment_query |= Q(
                publication__attached_contracts__contract__publication_billing="consolidated"
            )

        if InvoiceReceived in payment_statuses:
            payment_query |= Q(publication__payment__status="invoice_received")

        if PublicationPaid in payment_statuses:
            payment_query |= Q(publication__payment__status="paid")

        if PublicationUnpaid in payment_statuses:
            payment_query |= Q(publication__payment__isnull=True) & ~Q(
                publication__attached_contracts__contract__publication_billing="consolidated"
            )

        query = query & payment_query

    return (
        FundingRequestModel.objects.filter(query)
        .distinct()
        .select_related(
            "review",
            "publication__article_journal",
            "publication__monograph_publisher",
        )
        .prefetch_related(
            "labels",
            "publication__relevant_authors",
        )
        .order_by("-created_at")
    )


def get_funding_organization(pk: int) -> FundingOrganization:
    return FundingOrganization.objects.get(pk=pk)


def get_funding_organization_by_name(name: str) -> FundingOrganization | None:
    return FundingOrganization.objects.filter(name=name).first()
