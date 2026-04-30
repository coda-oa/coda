from collections.abc import Iterable, Sequence
from typing import Any, TypeIs

from django.db import transaction

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.fundingrequests import mapper as fundingrequest_mapper
from coda.apps.fundingrequests.mappers import FundingRequestDomainMapper
from coda.apps.fundingrequests.models import ExternalFunding as ExternalFundingModel
from coda.apps.fundingrequests.models import FundingOrganization, FundingRequestReview
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import FundingRequestContact as FundingRequestContactModel
from coda.apps.publications.repositories import publication_repository
from coda.domain.fundingrequest import (
    AnyFundingRequest,
    ExternalFunding,
    FundingRequest,
    FundingRequestContact,
    FundingRequestId,
    Payment,
    Review,
    TPublication,
)
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.fundingrequest.references import FundingRequestReference
from coda.domain.publication import Monograph, Publication, PublicationId


@transaction.atomic
def create(fundingrequest: AnyFundingRequest) -> FundingRequestId:
    if fundingrequest.id:
        raise FundingRequestAlreadyExists(fundingrequest.id)

    pid = publication_repository.create(fundingrequest.publication)
    fundingrequest.publication.id = pid
    fr = _save(fundingrequest)

    return FundingRequestId(fr.pk)


@transaction.atomic
def update(fundingrequest: AnyFundingRequest) -> None:
    if not fundingrequest.id:
        raise UnsavedFundingRequest(fundingrequest)

    publication_repository.update(fundingrequest.publication)
    _save(fundingrequest)


def _save(fundingrequest: AnyFundingRequest) -> FundingRequestModel:
    fr = fundingrequest_mapper.as_django_model(fundingrequest)
    fundingrequest_mapper.synchronize_relationships(fundingrequest, fr)
    fr.save()
    return fr


@transaction.atomic
def create_many(fundingrequests: Iterable[AnyFundingRequest]) -> Iterable[FundingRequestId]:
    fundingrequest_list = list(fundingrequests)
    reviews = FundingRequestReview.objects.bulk_create(
        [fundingrequest_mapper._create_review_model(fr._review) for fr in fundingrequest_list]
    )

    publications = [fundingrequest.publication for fundingrequest in fundingrequest_list]
    publication_ids = publication_repository.create_many(publications)
    fr_models = fundingrequest_mapper.create_bulk_models(
        fundingrequest_list, publication_ids, reviews
    )
    created_frs = FundingRequestModel.objects.bulk_create(fr_models)

    external_funding_objs = fundingrequest_mapper.create_bulk_external_funding_models(
        fundingrequest_list, created_frs
    )
    contact_objs, contact_map = fundingrequest_mapper.create_bulk_contact_models_and_map(
        fundingrequest_list, created_frs
    )

    if external_funding_objs:
        ExternalFundingModel.objects.bulk_create(external_funding_objs)

    if contact_objs:
        FundingRequestContactModel.objects.bulk_create(contact_objs)
        # Now update the extra_contact field using bulk_update
        for fr in created_frs:
            model_contact = contact_map.get(fr.pk)
            if model_contact:
                fr.extra_contact = model_contact

        # Bulk update only FRs that have contacts
        frs_to_update = [fr for fr in created_frs if fr.pk in contact_map]
        if frs_to_update:
            FundingRequestModel.objects.bulk_update(frs_to_update, fields=["extra_contact"])

    return tuple(FundingRequestId(fr.pk) for fr in created_frs)


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
    fundingrequest_mapper._update_review_model(review, review_model)
    review_model.save()


@transaction.atomic
def save_contact(id: FundingRequestId, contact: FundingRequestContact) -> None:
    fr = FundingRequestModel.objects.get(pk=id)
    fundingrequest_mapper._synchronize_contact(fr, contact)


@transaction.atomic
def save_funding(
    id: FundingRequestId,
    payment: Payment,
    funding: Iterable[ExternalFunding],
) -> None:
    fr = FundingRequestModel.objects.get(pk=id)

    fundingrequest_mapper.update_payment_fields(payment, fr)

    fr.save()

    # Update external funding
    fundingrequest_mapper._synchronize_external_funding(fr, funding)


def request_id_exists(request_id: PublicFundingRequestId) -> bool:
    return FundingRequestModel.objects.filter(request_id=str(request_id)).exists()


def get_request_id_for(id: FundingRequestId) -> PublicFundingRequestId:
    request_id, *_ = FundingRequestModel.objects.filter(pk=id).values_list("request_id").get()
    return PublicFundingRequestId.from_str(request_id)


def get_all_request_ids() -> list[str]:
    """Fetch all existing request IDs for bulk existence checking.

    Returns a list of all request_id strings from the database.
    Used to optimize batch operations that need to check ID uniqueness.
    """
    return list(FundingRequestModel.objects.values_list("request_id", flat=True))


def first() -> AnyFundingRequest | None:
    model = FundingRequestDomainMapper.prefetch(FundingRequestModel.objects.all()).first()
    return FundingRequestDomainMapper.map(model) if model else None


def get_by_id(id: FundingRequestId) -> AnyFundingRequest:
    model = FundingRequestDomainMapper.prefetch(FundingRequestModel.objects.all()).get(pk=id)
    return FundingRequestDomainMapper.map(model)


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
        FundingRequestDomainMapper.map,
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


def get_by_request_id(request_id: PublicFundingRequestId) -> AnyFundingRequest:
    model = FundingRequestDomainMapper.prefetch(FundingRequestModel.objects.all()).get(
        request_id=str(request_id)
    )
    return FundingRequestDomainMapper.map(model)


def find_reference_by_publication(publication: PublicationId) -> FundingRequestReference | None:
    model = FundingRequestModel.objects.filter(publication_id=publication).first()
    if not model:
        return None
    return FundingRequestReference(request_id=model.request_id, url=model.get_absolute_url())


def get_by_publication_id(publication_id: PublicationId) -> AnyFundingRequest:
    model = FundingRequestDomainMapper.prefetch(FundingRequestModel.objects.all()).get(
        publication_id=publication_id
    )
    return FundingRequestDomainMapper.map(model)


def _is_publication_type(
    fr: Any, publication_type: type[TPublication]
) -> TypeIs[FundingRequest[TPublication]]:
    return isinstance(fr, FundingRequest) and isinstance(fr.publication, publication_type)


def get_review(id: FundingRequestId) -> Review:
    model = FundingRequestReview.objects.filter(fundingrequest=id).first()
    return fundingrequest_mapper._as_review_domain_object(model, id)


def get_funding_organization(pk: int) -> FundingOrganization:
    return FundingOrganization.objects.get(pk=pk)


def get_funding_organization_by_name(name: str) -> FundingOrganization | None:
    return FundingOrganization.objects.filter(name=name).first()
