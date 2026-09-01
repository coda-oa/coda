import uuid
from collections.abc import Iterable

from django.db.models import Prefetch, QuerySet

from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.models import FundingAssignment, Invoice
from coda.apps.publications.models import Concept

type LabelId = int


def get_funding_requests_for_export(
    params: fundingrequest_query.FundingRequestSearchParams,
) -> QuerySet[FundingRequest]:
    criteria = fundingrequest_query.build_criteria(params)
    qs = fundingrequest_query.search(*criteria)

    return (
        qs.select_related(
            "publication",
            "review",
            "extra_contact",
        )
        .prefetch_related(
            Prefetch(
                "publication__position_set__invoice",
                queryset=Invoice.objects.select_related("creditor").prefetch_related(
                    "currency_conversions",
                    "positions__funding_assignments__funding_source",
                    "positions__publication",
                    "positions__contract",
                ),
            ),
            "publication__position_set__invoice__creditor",
            "publication__position_set__invoice__currency_conversions",
            "publication__position_set__invoice__positions",
            "publication__position_set__invoice__positions__funding_assignments",
            "publication__position_set__invoice__positions__funding_assignments__funding_source",
            "publication__links",
            "publication__links__type",
            "publication__attached_contracts",
            "publication__attached_contracts__contract",
            "publication__subject_area",
            "publication__subject_area__vocabulary",
            "publication__publication_type",
            "publication__publication_type__vocabulary",
            "labels",
            "external_funding",
            "external_funding__organization",
            Prefetch(
                "publication__position_set__funding_assignments",
                queryset=FundingAssignment.objects.select_related("funding_source"),
            ),
        )
        .distinct()
    )


def get_concept_id_lookup(
    funding_requests: Iterable[FundingRequest],
) -> dict[uuid.UUID, str]:
    entity_ids = {
        attached.entity_id
        for funding_request in funding_requests
        for attached in (
            funding_request.publication.subject_area,
            funding_request.publication.publication_type,
        )
        if attached is not None
    }

    return dict(
        Concept.objects.filter(entity_id__in=entity_ids).values_list("entity_id", "concept_id")
    )
