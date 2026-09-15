from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from coda.apps.fundingrequests.repository import save_review
from coda.apps.invoices.models import FundingAssignment, Position
from coda.apps.opencost.data_aggregation import (
    fetch_contracts_by_ids,
    fetch_invoices_by_ids,
    fetch_publications_by_ids,
    get_contracts_for_period,
    get_invoices_for_period,
    get_publications_for_period,
    key_by_id,
    select_contract_ids,
    select_publication_ids,
)
from coda.apps.publications.models import AttachedContract
from coda.domain.fundingrequest import FundingRequestId, Review
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money
from tests import modelfactory
from tests.exports.fundingrequest_csv.helpers import _make_params
from tests.opencost.helpers import (
    create_contract_with_invoice,
    create_creditor,
    create_invoice,
    create_position,
    create_publication_with_invoice,
)


@pytest.mark.django_db
def test__publications_of_different_dates__querying_specific_time_range__only_returns_publications_in_range() -> (
    None
):
    publication_before_period = modelfactory.publication(title="Before Period")
    publication_in_period_1 = modelfactory.publication(title="In Period 1")
    publication_in_period_2 = modelfactory.publication(title="In Period 2")
    publication_after_period = modelfactory.publication(title="After Period")

    create_publication_with_invoice(
        publication_before_period,
        invoice_date=date(2023, 1, 20),
        invoice_number="INV-BEFORE",
        cost_amount=Decimal("1000.00"),
        cost_type="APC",
    )
    create_publication_with_invoice(
        publication_in_period_1,
        invoice_date=date(2023, 2, 10),
        invoice_number="INV-1",
        cost_amount=Decimal("1000.00"),
        cost_type="APC",
    )
    create_publication_with_invoice(
        publication_in_period_2,
        invoice_date=date(2023, 2, 25),
        invoice_number="INV-2",
        cost_amount=Decimal("1000.00"),
        cost_type="APC",
    )
    create_publication_with_invoice(
        publication_after_period,
        invoice_date=date(2023, 3, 10),
        invoice_number="INV-AFTER",
        cost_amount=Decimal("1000.00"),
        cost_type="APC",
    )

    query_results = get_publications_for_period(
        _make_params(
            date(2023, 2, 1),
            date(2023, 2, 28),
        )
    )

    assert publication_in_period_1 in query_results
    assert publication_in_period_2 in query_results
    assert publication_before_period not in query_results
    assert publication_after_period not in query_results


@pytest.mark.django_db
def test__publication_with_invoice__querying_data__invoice_data_is_available() -> None:
    publication = modelfactory.publication(title="Publication with Invoice")
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="12345",
        creditor_name="Creditor Name",
        cost_amount=Decimal("1500.00"),
        cost_type="APC",
    )

    results = get_publications_for_period(
        _make_params(
            date(2024, 6, 1),
            date(2024, 6, 30),
        )
    )

    assert publication in results

    pub = results.first()
    assert pub is not None
    positions = list(pub.position_set.all())
    assert len(positions) == 1
    assert positions[0].invoice.number == "12345"
    assert positions[0].invoice.creditor.name == "Creditor Name"
    assert positions[0].cost_amount == Decimal("1500.00")


@pytest.mark.django_db
def test__invoices_with_different_dates__querying_specific_time_range__only_returns_invoices_in_range() -> (
    None
):
    creditor_a = create_creditor(name="Creditor A")
    invoice_before_period = create_invoice(
        creditor=creditor_a,
        invoice_date=date(2023, 1, 15),
        number="INV-001",
    )

    creditor_b = create_creditor(name="Creditor B")
    invoice_in_period_1 = create_invoice(
        creditor=creditor_b,
        invoice_date=date(2023, 2, 10),
        number="INV-002",
    )

    creditor_c = create_creditor(name="Creditor C")
    invoice_in_period_2 = create_invoice(
        creditor=creditor_c,
        invoice_date=date(2023, 2, 20),
        number="INV-003",
    )

    creditor_d = create_creditor(name="Creditor D")
    invoice_after_period = create_invoice(
        creditor=creditor_d,
        invoice_date=date(2023, 3, 5),
        number="INV-004",
    )

    query_results = get_invoices_for_period(
        start_date=date(2023, 2, 1),
        end_date=date(2023, 2, 28),
    )

    assert invoice_in_period_1 in query_results
    assert invoice_in_period_2 in query_results
    assert invoice_before_period not in query_results
    assert invoice_after_period not in query_results


@pytest.mark.django_db
def test__paid_and_unpaid_invoices__querying_invoices_for_period__returns_only_paid_invoices() -> (
    None
):
    creditor = create_creditor(name="Creditor E")
    paid_invoice = create_invoice(
        creditor=creditor,
        invoice_date=date(2024, 5, 15),
        number="INV-PAID",
        status="paid",
    )
    unpaid_invoice = create_invoice(
        creditor=creditor,
        invoice_date=date(2024, 5, 20),
        number="INV-UNPAID",
        status="unpaid",
    )

    query_results = get_invoices_for_period(
        start_date=date(2024, 5, 1),
        end_date=date(2024, 5, 31),
    )

    assert paid_invoice in query_results
    assert unpaid_invoice not in query_results


@pytest.mark.django_db
def test_get_publications_for_period_works_without_invoice_parameter() -> None:
    """
    Verify backward compatibility: function should still work when called
    without the invoices_in_period parameter.
    """
    # Create test data
    publication = modelfactory.publication(title="Test Publication")
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-TEST",
        cost_amount=Decimal("1000.00"),
        cost_type="APC",
    )

    # Call without invoice parameter (backward compatibility)
    publications = get_publications_for_period(
        _make_params(
            date(2024, 1, 1),
            date(2024, 12, 31),
        )
    )

    # Should still work
    assert publications.count() == 1
    assert publication in publications


@pytest.mark.django_db
def test_get_publications_for_period_works_with_invoice_parameter() -> None:
    """
    Verify new parameter works: function accepts pre-fetched invoices.
    """
    # Create test data
    publication = modelfactory.publication(title="Test Publication")
    create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-TEST",
        cost_amount=Decimal("1000.00"),
        cost_type="APC",
    )

    # Fetch invoices separately
    invoices = get_invoices_for_period(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    # Call with invoice parameter
    publications = get_publications_for_period(
        _make_params(date(2024, 1, 1), date(2024, 12, 31)),
        invoices_in_period=invoices,
    )

    # Should work with passed invoices
    assert publications.count() == 1
    assert publication in publications


@pytest.mark.django_db
def test_get_contracts_for_period_works_without_invoice_parameter() -> None:
    """
    Verify backward compatibility: function should still work when called
    without the invoices_in_period parameter.
    """
    # Create test data
    contract = modelfactory.contract()
    contract.start_date = date(2024, 1, 1)
    contract.end_date = date(2024, 12, 31)
    contract.save()

    create_contract_with_invoice(
        contract,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-CONTRACT",
    )

    # Call without invoice parameter (backward compatibility)
    contracts = get_contracts_for_period(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    # Should still work
    assert contracts.count() == 1
    assert contract in contracts


@pytest.mark.django_db
def test_get_contracts_for_period_works_with_invoice_parameter() -> None:
    """
    Verify new parameter works: function accepts pre-fetched invoices.
    """
    # Create test data
    contract = modelfactory.contract()
    contract.start_date = date(2024, 1, 1)
    contract.end_date = date(2024, 12, 31)
    contract.save()

    create_contract_with_invoice(
        contract,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-CONTRACT",
    )

    # Fetch invoices separately
    invoices = get_invoices_for_period(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    # Call with invoice parameter
    contracts = get_contracts_for_period(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        invoices_in_period=invoices,
    )

    # Should work with passed invoices
    assert contracts.count() == 1
    assert contract in contracts


@pytest.mark.django_db
def test__review_result_filter__querying_publications_for_period__returns_only_matching_publications() -> (
    None
):
    fr_approved = modelfactory.fundingrequest()
    fr_rejected = modelfactory.fundingrequest()

    save_review(
        Review(FundingRequestId(fr_approved.id)).update_review(
            ReviewResult.Approved,
            Money(Decimal("1000.00"), Currency.EUR),
        )
    )
    save_review(Review(FundingRequestId(fr_rejected.id)).update_review(ReviewResult.Rejected))

    create_publication_with_invoice(
        fr_approved.publication,
        invoice_date=date(2024, 6, 10),
        invoice_number="INV-APPROVED",
    )
    create_publication_with_invoice(
        fr_rejected.publication,
        invoice_date=date(2024, 6, 11),
        invoice_number="INV-REJECTED",
    )

    publications = get_publications_for_period(
        _make_params(
            date(2024, 6, 1),
            date(2024, 6, 30),
            review_results=[ReviewResult.Approved],
        )
    )

    assert fr_approved.publication in publications
    assert fr_rejected.publication not in publications


@pytest.mark.django_db
def test__select_and_fetch_publications_by_ids__matches_get_publications_for_period() -> None:
    publication = modelfactory.publication(title="In Period")
    _, in_period_position = create_publication_with_invoice(
        publication,
        invoice_date=date(2024, 6, 10),
        invoice_number="INV-IN",
        cost_amount=Decimal("1000.00"),
    )
    outside = modelfactory.publication(title="Out Of Period")
    create_publication_with_invoice(
        outside,
        invoice_date=date(2024, 8, 10),
        invoice_number="INV-OUT",
    )
    # A later position on the in-period publication, on an out-of-period invoice:
    # the by-ids fetch sees it live, the period-bound fetch must not.
    late_invoice = create_invoice(
        creditor=create_creditor(name="Late Creditor"),
        invoice_date=date(2024, 9, 1),
        number="INV-LATE",
    )
    late_position = create_position(
        late_invoice, publication=publication, cost_amount=Decimal("500.00")
    )
    # Attachment years are created newest-first to prove the pinned order.
    AttachedContract.objects.create(
        publication=publication, contract=modelfactory.contract(), contract_year=2024
    )
    AttachedContract.objects.create(
        publication=publication, contract=modelfactory.contract(), contract_year=2023
    )

    params = _make_params(date(2024, 6, 1), date(2024, 6, 30))

    assert select_publication_ids(params) == {publication.id}

    by_period = key_by_id(get_publications_for_period(params))
    fetched = key_by_id(fetch_publications_by_ids(select_publication_ids(params)))

    # Same objects as the by-period fetch ...
    assert set(fetched) == set(by_period) == {publication.id}
    # ... while the default fetch re-reads positions live (out-of-period included),
    # pinned by (cost_amount, id) ...
    assert [p.id for p in fetched[publication.id].position_set.all()] == [
        late_position.id,
        in_period_position.id,
    ]
    # ... and attached contracts are pinned by contract_year.
    assert [ac.contract_year for ac in fetched[publication.id].attached_contracts.all()] == [
        2023,
        2024,
    ]

    # With the period-bound positions override it matches get_publications_for_period
    # position-for-position.
    invoices_in_period = get_invoices_for_period(date(2024, 6, 1), date(2024, 6, 30))
    positions_in_period = Position.objects.filter(invoice__in=invoices_in_period).select_related(
        "invoice", "invoice__creditor"
    )
    bounded = key_by_id(
        fetch_publications_by_ids(select_publication_ids(params), positions=positions_in_period)
    )
    pub = bounded[publication.id]
    assert (
        [p.id for p in pub.position_set.all()]
        == [p.id for p in by_period[publication.id].position_set.all()]
        == [in_period_position.id]
    )

    positions = list(pub.position_set.all())
    with CaptureQueriesContext(connection) as ctx:
        assert positions[0].invoice.creditor.name is not None
        assert pub.article_journal is not None
        assert pub.article_journal.publisher is not None
        assert list(pub.links.all()) == []
        assert list(pub.relevant_authors.all()) == []
        assert len(list(pub.attached_contracts.all())) == 2
    assert ctx.captured_queries == []


@pytest.mark.django_db
def test__select_and_fetch_contracts_by_ids__matches_get_contracts_for_period() -> None:
    contract = modelfactory.contract()
    contract.start_date = date(2024, 1, 1)
    contract.end_date = date(2024, 12, 31)
    contract.save()
    _invoice, (higher, lower) = create_contract_with_invoice(
        contract,
        invoice_date=date(2024, 6, 15),
        invoice_number="INV-CONTRACT",
        position_descriptions=["Higher amount", "Lower amount"],
        position_amounts=[Decimal("2000.00"), Decimal("1000.00")],
    )
    # A later position on an out-of-period invoice: live-only, not period-bound.
    later_invoice = create_invoice(invoice_date=date(2024, 9, 1), number="INV-CONTRACT-LATE")
    late_position = create_position(
        later_invoice, contract=contract, cost_amount=Decimal("3000.00")
    )

    start, end = date(2024, 6, 1), date(2024, 6, 30)

    assert select_contract_ids(start, end) == {contract.id}
    assert select_contract_ids(start, end, contract=contract.id) == {contract.id}

    by_period = key_by_id(get_contracts_for_period(start_date=start, end_date=end))

    invoices_in_period = get_invoices_for_period(start, end)
    positions_in_period = Position.objects.filter(
        invoice__in=invoices_in_period, contract__isnull=False
    ).select_related("invoice", "invoice__creditor")
    bounded = key_by_id(
        fetch_contracts_by_ids(select_contract_ids(start, end), positions=positions_in_period)
    )

    # Same objects as the by-period fetch, with the same period-bound positions,
    # pinned by (cost_amount, id).
    assert set(bounded) == set(by_period) == {contract.id}
    assert (
        [p.id for p in bounded[contract.id].position_set.all()]
        == [p.id for p in by_period[contract.id].position_set.all()]
        == [lower.id, higher.id]
    )

    # The default fetch re-reads positions live, out-of-period included.
    live = key_by_id(fetch_contracts_by_ids(select_contract_ids(start, end)))
    assert [p.id for p in live[contract.id].position_set.all()] == [
        lower.id,
        higher.id,
        late_position.id,
    ]

    fetched = bounded[contract.id]
    positions = list(fetched.position_set.all())
    with CaptureQueriesContext(connection) as ctx:
        assert list(fetched.publishers.all()) == []
        assert list(fetched.journals.all()) == []
        assert list(fetched.links.all()) == []
        for p in positions:
            assert p.invoice.creditor.name is not None
    assert ctx.captured_queries == []


@pytest.mark.django_db
def test__fetch_invoices_by_ids__returns_given_ids_regardless_of_period_and_status() -> None:
    creditor = create_creditor(name="Fetch Creditor")
    paid_in_period = create_invoice(
        creditor=creditor, invoice_date=date(2024, 6, 10), number="INV-F1"
    )
    unpaid_in_period = create_invoice(
        creditor=creditor, invoice_date=date(2024, 6, 20), number="INV-F2", status="unpaid"
    )
    paid_outside_period = create_invoice(
        creditor=creditor, invoice_date=date(2024, 9, 5), number="INV-F3"
    )
    not_pinned = create_invoice(creditor=creditor, invoice_date=date(2024, 6, 25), number="INV-F4")

    publication = modelfactory.publication(title="Fetched Invoice Publication")
    position = create_position(
        paid_in_period, publication=publication, cost_amount=Decimal("1200.00")
    )
    assignment = FundingAssignment.objects.create(position=position, amount=Decimal("1200.00"))

    # Unpaid and out-of-period invoices come back by id; unlisted ones never do.
    fetched = key_by_id(
        fetch_invoices_by_ids([paid_in_period.id, unpaid_in_period.id, paid_outside_period.id])
    )

    assert set(fetched) == {paid_in_period.id, unpaid_in_period.id, paid_outside_period.id}
    assert not_pinned.id not in fetched

    invoice = fetched[paid_in_period.id]
    positions = list(invoice.positions.all())
    assert [p.id for p in positions] == [position.id]

    # Same prefetch shape as get_invoices_for_period: everything below is cached.
    with CaptureQueriesContext(connection) as ctx:
        assert invoice.creditor.name == "Fetch Creditor"
        assert positions[0].publication is not None
        assert positions[0].publication.article_journal is not None
        assert positions[0].publication.article_journal.publisher is not None
        assert list(positions[0].funding_assignments.all()) == [assignment]
    assert ctx.captured_queries == []
