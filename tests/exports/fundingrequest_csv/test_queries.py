# tests/exports/fundingrequest_csv/test_queries.py

import uuid
from datetime import date
from decimal import Decimal

import pytest
from pytest_django import DjangoAssertNumQueries

from coda.apps.exports.services.fundingrequest_csv.queries import (
    get_concept_id_lookup,
    get_funding_requests_for_export,
)
from coda.apps.fundingrequests import fundingrequest_query, repository
from coda.apps.invoices import funding_source_repository
from coda.apps.publications.models import PublicationPayment
from coda.contexts.finance.services import invoice_service
from coda.domain.finance.invoice import CreditorId, FundingSourceId
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.fundingrequest.review import Review, ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.publication.publication import PublicationId
from tests import domainfactory, modelfactory
from tests.exports.fundingrequest_csv.helpers import (
    _make_params,
    create_funding_request_with_concepts,
    create_invoice_with_publication_position,
)


@pytest.mark.django_db
def test__funding_requests_with_different_request_dates__query_for_export__returns_only_matching_funding_requests() -> (
    None
):
    fr_march = modelfactory.fundingrequest(title="March FR")
    fr_march.request_date = date(2026, 3, 15)
    fr_march.save()

    fr_june = modelfactory.fundingrequest(title="June FR")
    fr_june.request_date = date(2026, 6, 15)
    fr_june.save()

    results = get_funding_requests_for_export(_make_params(date(2026, 3, 1), date(2026, 3, 31)))

    assert list(results) == [fr_march]


@pytest.mark.django_db
def test__funding_request_with_multiple_authors__query_for_export__authors_returned_in_id_order() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Multi author FR")
    fr.request_date = date(2026, 3, 15)
    fr.save()
    fr.publication.relevant_authors.all().delete()

    authors_in_id_order = sorted(
        (modelfactory.author() for _ in range(3)), key=lambda author: author.pk
    )
    for author in authors_in_id_order:
        author.publication = fr.publication
        author.save()

    results = get_funding_requests_for_export(_make_params(date(2026, 3, 1), date(2026, 3, 31)))

    export_authors = list(results[0].publication.relevant_authors.all())
    assert export_authors == authors_in_id_order


@pytest.mark.django_db
@pytest.mark.performance
def test__funding_request_with_author_affiliation_and_identifier__query_for_export__fetches_authors_without_extra_queries(
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """Author prefetch (with identifier and affiliation) costs a single query, no N+1."""
    fr = modelfactory.fundingrequest(title="Query count FR")
    fr.request_date = date(2026, 3, 15)
    fr.save()
    institution = modelfactory.institution()
    extra_author = modelfactory.author()
    extra_author.publication = fr.publication
    extra_author.affiliation = institution
    extra_author.save()

    with django_assert_num_queries(12):
        results = get_funding_requests_for_export(_make_params(date(2026, 3, 1), date(2026, 3, 31)))
        for funding_request in results:
            for author in funding_request.publication.relevant_authors.all():
                _ = author.name
                _ = author.identifier.orcid if author.identifier else None
                _ = author.affiliation.name if author.affiliation else None


@pytest.mark.django_db
def test__funding_requests_with_different_review_results__query_with_review_filter__returns_only_matching() -> (
    None
):
    fr_approved = modelfactory.fundingrequest(title="Approved FR")
    fr_approved.request_date = date(2026, 3, 10)
    fr_approved.save()
    repository.save_review(
        Review(FundingRequestId(fr_approved.id)).update_review(
            ReviewResult.Approved, Money(Decimal("1000.00"), Currency.EUR)
        )
    )

    fr_rejected = modelfactory.fundingrequest(title="Rejected FR")
    fr_rejected.request_date = date(2026, 3, 20)
    fr_rejected.save()
    repository.save_review(
        Review(FundingRequestId(fr_rejected.id)).update_review(ReviewResult.Rejected)
    )

    results = get_funding_requests_for_export(
        _make_params(
            date(2026, 3, 1),
            date(2026, 3, 31),
            review_results=[ReviewResult.Approved],
        )
    )

    assert list(results) == [fr_approved]


@pytest.mark.django_db
def test__funding_requests_with_different_payment_statuses__query_with_payment_status_filter__returns_only_matching() -> (
    None
):
    fr_paid = modelfactory.fundingrequest(title="Paid FR")
    fr_paid.request_date = date(2026, 3, 10)
    fr_paid.save()
    PublicationPayment.objects.create(publication=fr_paid.publication, status="paid")

    fr_invoice_received = modelfactory.fundingrequest(title="Invoice Received FR")
    fr_invoice_received.request_date = date(2026, 3, 12)
    fr_invoice_received.save()
    PublicationPayment.objects.create(
        publication=fr_invoice_received.publication,
        status="invoice_received",
    )

    results = get_funding_requests_for_export(
        _make_params(
            date(2026, 3, 1),
            date(2026, 3, 31),
            payment_statuses=[fundingrequest_query.PaymentStatus.Paid],
        )
    )

    assert list(results) == [fr_paid]


@pytest.mark.django_db
def test__combining_funding_request_and_invoice_filters__query_with_combined_filters__returns_only_matching_all_criteria() -> (
    None
):
    fr1 = modelfactory.fundingrequest(title="FR 1 - Match All")
    fr1.request_date = date(2026, 3, 5)
    fr1.save()
    repository.save_review(
        Review(FundingRequestId(fr1.id)).update_review(
            ReviewResult.Approved, Money(Decimal("1000.00"), Currency.EUR)
        )
    )
    invoice1 = create_invoice_with_publication_position(fr1)
    invoice_position = next(iter(invoice1.positions))
    invoice_position.cost.amount = Decimal("1500.00")
    funding_source_1 = domainfactory.budget()
    funding_source_1.id = funding_source_repository.create(funding_source_1)
    invoice_position.assign_funding(funding_source_1, Decimal("1000.00"))
    invoice_service.save(invoice1)

    fr2 = modelfactory.fundingrequest(title="FR 2 - Wrong Status")
    fr2.request_date = date(2026, 3, 10)
    fr2.save()
    repository.save_review(
        Review(FundingRequestId(fr2.id)).update_review(
            ReviewResult.Approved, Money(Decimal("2000.00"), Currency.EUR)
        )
    )
    create_invoice_with_publication_position(fr2)

    fr3 = modelfactory.fundingrequest(title="FR 3 - Wrong Review")
    fr3.request_date = date(2026, 3, 15)
    fr3.save()
    repository.save_review(Review(FundingRequestId(fr3.id)).update_review(ReviewResult.Rejected))
    create_invoice_with_publication_position(fr3)

    results = get_funding_requests_for_export(
        _make_params(
            date(2026, 3, 1),
            date(2026, 3, 31),
            review_results=[ReviewResult.Approved],
            funding_source=FundingSourceId(funding_source_1.id),
        )
    )

    assert list(results) == [fr1]


@pytest.mark.django_db
def test__shared_invoice_with_foreign_position__query_with_funding_source__is_publication_scoped_not_invoice_scoped() -> (
    None
):
    """Request-level half of the funding-source filter.

    The Q object matches a funding request whose publication has *any*
    position row carrying the source — it is publication-scoped and cannot
    scope to a specific invoice. Fixture: B funds one of its own positions
    on a private invoice; B's *other* position sits unfunded on a shared
    invoice whose source-carrying position belongs to publication C; D
    shares that invoice but has no funded position anywhere. The query
    layer admits B and C but excludes D: publication-scoping excludes D,
    invoice-scoping would admit it. Dropping the shared invoice from B's
    export is the mapper's job — see _has_funding_source in
    apps/exports/services/fundingrequest_csv/mappers.py and the shared-
    invoice filtering test in tests/exports/fundingrequest_csv/ that pins
    the combined behavior (B's export shows its private invoice only).
    """
    funding_request_b = modelfactory.fundingrequest(title="Query Scope B")
    funding_request_b.request_date = date(2026, 3, 5)
    funding_request_b.save()

    funding_request_c = modelfactory.fundingrequest(title="Query Scope C")
    funding_request_c.request_date = date(2026, 3, 10)
    funding_request_c.save()

    # D shares the shared invoice but has no funded position of its own:
    # publication-scoping excludes it, invoice-scoping would admit it.
    funding_request_d = modelfactory.fundingrequest(title="Query Scope D Unfunded")
    funding_request_d.request_date = date(2026, 3, 15)
    funding_request_d.save()

    funding_source_x = domainfactory.budget()
    funding_source_x.id = funding_source_repository.create(funding_source_x)
    creditor_id = CreditorId(modelfactory.creditor().pk)

    # Shared invoice: C's position carries source X, B's and D's do not.
    position_b_on_shared = domainfactory.publication_position(
        PublicationId(funding_request_b.publication.id), currency=Currency.EUR
    )
    position_c = domainfactory.publication_position(
        PublicationId(funding_request_c.publication.id), currency=Currency.EUR
    )
    position_d_on_shared = domainfactory.publication_position(
        PublicationId(funding_request_d.publication.id), currency=Currency.EUR
    )
    position_c.assign_funding(funding_source_x, position_c.cost.amount)
    shared_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[position_b_on_shared, position_c, position_d_on_shared],
    )
    shared_invoice.id = invoice_service.save(shared_invoice)

    # B's private invoice: its own position carries source X.
    position_b_private = domainfactory.publication_position(
        PublicationId(funding_request_b.publication.id), currency=Currency.EUR
    )
    position_b_private.assign_funding(funding_source_x, position_b_private.cost.amount)
    private_invoice = domainfactory.invoice(
        creditor=creditor_id,
        positions=[position_b_private],
    )
    private_invoice.id = invoice_service.save(private_invoice)

    results = get_funding_requests_for_export(
        _make_params(
            date(2026, 3, 1),
            date(2026, 3, 31),
            funding_source=FundingSourceId(funding_source_x.id),
        )
    )

    # The query layer includes B (via its funded private position) and C
    # (via its position on the shared invoice) — but not D, whose only
    # position is the unfunded one on the shared invoice. An invoice-scoped
    # criterion would admit D too; this pins publication-scoping.
    # Whether the shared invoice appears in B's export is invisible here —
    # that scoping is deliberately left to the mapper layer.
    # (default sort is request_date descending)
    assert list(results) == [funding_request_c, funding_request_b]
    assert funding_request_d not in results


@pytest.mark.django_db
def test__query_with_prefetch__accessing_related_objects__does_not_trigger_additional_queries() -> (
    None
):
    """Verify prefetch_related prevents N+1 query problems."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    # Arrange: Create 3 funding requests with March request dates, invoices and positions
    _create_three_fundingrequests_for_performance_check()

    # Act: Query and access all prefetched relationships
    with CaptureQueriesContext(connection) as context:
        results = get_funding_requests_for_export(
            _make_params(
                date(2026, 3, 1),
                date(2026, 3, 31),
            )
        )

        # Access all prefetched relationships - should NOT trigger additional queries
        for fr in results:
            for position in fr.publication.position_set.all():
                _ = position.invoice.creditor.name  # Accessing creditor (prefetched)
                _ = position.invoice.date  # Accessing invoice (prefetched)
                for conversion in position.invoice.currency_conversions.all():  # Prefetched
                    _ = conversion.id
                for assignment in position.funding_assignments.all():  # Prefetched
                    if assignment.funding_source:  # Handle optional
                        _ = assignment.funding_source.name  # Accessing funding source (prefetched)

    # Assert: Query count should be low (not N+1)
    # Expected queries:
    # 1. Main FundingRequest query with filters
    # 2. Prefetch publication.position_set
    # 3. Prefetch position.invoice
    # 4. Prefetch invoice.creditor
    # 5. Prefetch invoice.currency_conversions
    # 6. Prefetch position.funding_assignments
    # 7. Prefetch funding_assignments.funding_source
    # Should be around 7-10 queries total, NOT 3 * 2 * N separate queries
    query_count = len(context.captured_queries)
    assert query_count < 25, (
        f"Too many queries: {query_count}. Prefetch may not be working correctly."
    )


@pytest.mark.django_db
def test__funding_request_with_invoice__query_for_export__fetch_plan_is_pinned() -> None:
    """The export query fetches every invoice-related relation without N+1:
    accessing the prefetched relations must not exceed this upper cap."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    fr = modelfactory.fundingrequest(title="Fetch Plan FR")
    fr.request_date = date(2026, 3, 15)
    fr.save()

    create_invoice_with_publication_position(fr)

    with CaptureQueriesContext(connection) as context:
        results = list(
            get_funding_requests_for_export(_make_params(date(2026, 3, 1), date(2026, 3, 31)))
        )
        for funding_request in results:
            for position in funding_request.publication.position_set.all():
                _ = position.invoice.creditor.name
                _ = position.invoice.date
                for conversion in position.invoice.currency_conversions.all():
                    _ = conversion.id
                for invoice_position in position.invoice.positions.all():
                    _ = invoice_position.cost_amount
                    for assignment in invoice_position.funding_assignments.all():
                        if assignment.funding_source:
                            _ = assignment.funding_source.name
                for assignment in position.funding_assignments.all():
                    if assignment.funding_source:
                        _ = assignment.funding_source.name

    assert len(context.captured_queries) <= 20, (
        f"Too many queries: {len(context.captured_queries)}. "
        "The export fetch plan regressed (N+1 or redundant prefetch)."
    )


@pytest.mark.django_db
def test__funding_requests_with_vocabulary_concepts__get_concept_id_lookup__maps_entity_ids_to_concept_ids() -> (
    None
):
    fr1 = create_funding_request_with_concepts(title="FR 1")
    fr2 = create_funding_request_with_concepts(title="FR 2")

    lookup = get_concept_id_lookup([fr1.funding_request, fr2.funding_request])

    assert lookup[fr1.subject_area_concept.entity_id] == fr1.subject_area_concept.concept_id
    assert lookup[fr1.publication_type_concept.entity_id] == fr1.publication_type_concept.concept_id
    assert lookup[fr2.subject_area_concept.entity_id] == fr2.subject_area_concept.concept_id
    assert lookup[fr2.publication_type_concept.entity_id] == fr2.publication_type_concept.concept_id


@pytest.mark.django_db
def test__funding_request_with_orphaned_concept__get_concept_id_lookup__omits_unresolvable_concepts() -> (
    None
):
    fr = create_funding_request_with_concepts(title="Orphaned FR")
    fr.funding_request.publication.subject_area.entity_id = uuid.uuid4()
    fr.funding_request.publication.subject_area.save()

    lookup = get_concept_id_lookup([fr.funding_request])

    assert fr.funding_request.publication.subject_area.entity_id not in lookup
    assert lookup[fr.publication_type_concept.entity_id] == fr.publication_type_concept.concept_id


def _create_three_fundingrequests_for_performance_check() -> None:
    for i in range(3):
        fr = modelfactory.fundingrequest(title=f"FR {i + 1}")
        fr.request_date = date(2026, 3, 5 + i)
        fr.save()
        creditor = modelfactory.creditor(name=f"Creditor {i + 1}")

        positions = []
        for j in range(2):
            position = domainfactory.publication_position(PublicationId(fr.publication.id))
            budget_model = modelfactory.budget(name=f"Budget {i + 1}-{j + 1}")
            funding_source = domainfactory.budget(FundingSourceId(budget_model.pk))
            position.assign_remaining(funding_source)
            positions.append(position)

        invoice = domainfactory.invoice(
            creditor=CreditorId(creditor.pk),
            positions=positions,
        )
        invoice_service.save(invoice)
