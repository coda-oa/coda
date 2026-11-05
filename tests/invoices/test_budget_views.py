from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.institutions.models import Institution
from coda.apps.invoices import budget_query
from coda.apps.invoices import repository as invoice_repository
from coda.apps.invoices.models import FundingSource
from coda.domain.money import Currency, Money
from tests import modelfactory
from tests.invoices import budget_setup

EUR = Currency.EUR
USD = Currency.USD


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_list__shows_status_chip_and_available(client: Client) -> None:
    budget, _ = budget_setup.a_budget(name="DARK 2026", amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("2500", EUR), budget, paid=True)
    exceeded, _ = budget_setup.a_budget(name="Overdrawn", amount=Money("1000", EUR))
    budget_setup.an_invoice_with_assignment(Money("1200", EUR), exceeded, paid=True)

    response = client.get(reverse("invoices:fundingsource_list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "DARK 2026" in content
    assert "Overdrawn" in content
    assert "within budget" in content
    assert "exceeded" in content
    assert "7500" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_list__shows_pending_conversion_chip(client: Client) -> None:
    budget, _ = budget_setup.a_budget(name="Rate Pending", amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(
        Money("3000", USD), budget, paid=True
    )  # no bank rate entered: pending conversion

    response = client.get(reverse("invoices:fundingsource_list"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Rate Pending" in content
    assert "pending conversion" in content
    assert "3000" in content  # pending amount in original currency


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__institution_source__name_matching_a_budget__update_passes(client: Client) -> None:
    """The uniqueness rule covers budget-type sources only; an institution
    row sharing a budget's name must not fail form validation (the partial
    index doesn't constrain it either)."""
    from coda.apps.invoices.models import FundingSource

    budget_setup.a_budget(name="DARK 2026")
    institution = modelfactory.institution()
    source = FundingSource.objects.create(
        type="institution", name="DARK 2026", institution_id=institution.pk
    )

    response = client.post(
        reverse("invoices:fundingsource_update", kwargs={"pk": source.pk}),
        {"name": "DARK 2026"},
    )

    assert response.status_code == 302
    source.refresh_from_db()
    assert source.name == "DARK 2026"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_detail__still_counts_own_review_splits_as_reserved(client: Client) -> None:
    """The display exclusion is opt-in to the review page: the budget detail
    page's default semantics keep counting a review's committed splits as
    reserved."""
    budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()

    from coda.contexts.fundingrequest.dto.commands import ReviewSplitDto, UpdateReviewDto
    from coda.contexts.fundingrequest.services import fundingrequests as fr_services
    from coda.domain.fundingrequest import FundingRequestId

    fr_services.update_review(
        FundingRequestId(funding_request.pk),
        UpdateReviewDto(
            decided_funding_amount=Decimal(600),
            decided_funding_currency="EUR",
            reviewer_remarks="",
            result="approved",
            funding_splits=[ReviewSplitDto(funding_source_id=budget_id, amount=Decimal(600))],
        ),
    )

    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": budget_id}))

    assert response.status_code == 200
    assert b"600.00" in response.content  # reserved figure on the detail page


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_detail__shows_full_state_and_ledger(client: Client) -> None:
    budget, budget_id = budget_setup.a_budget(name="DARK 2026", amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("2500", EUR), budget, paid=True)

    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": budget_id}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "DARK 2026" in content
    assert "10000" in content  # amount
    assert "2500" in content  # spent
    assert "7500" in content  # available
    assert "Period:" in content
    assert "2026" in content  # period year
    assert "ledger" in content.lower()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_transfer__books_transfer_and_shows_in_balances(client: Client) -> None:
    _source, source_id = budget_setup.a_budget(name="Source", amount=Money("5000", EUR))
    _target, _target_id = budget_setup.a_budget(name="Target", amount=Money("10000", EUR))

    response = client.post(
        reverse("invoices:budget_transfer", kwargs={"pk": source_id}),
        {"target": str(_target.id), "amount": "2000", "provenance_note": "top-up"},
    )

    assert response.status_code == 302
    from coda.apps.invoices.models import BudgetTransfer

    assert BudgetTransfer.objects.count() == 1
    assert budget_query.budget_balances(source_id).debit == Money("2000", EUR)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_transfer__beyond_capacity__renders_error(client: Client) -> None:
    _source, source_id = budget_setup.a_budget(name="Source", amount=Money("1000", EUR))
    _target, _target_id = budget_setup.a_budget(name="Target", amount=Money("10000", EUR))

    response = client.post(
        reverse("invoices:budget_transfer", kwargs={"pk": source_id}),
        {"target": str(_target.id), "amount": "1001", "provenance_note": ""},
    )

    assert response.status_code == 200
    assert b"exceeds its capacity" in response.content
    from coda.apps.invoices.models import BudgetTransfer

    assert BudgetTransfer.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_transfer__garbage_amount__renders_error_and_books_nothing(client: Client) -> None:
    _source, source_id = budget_setup.a_budget(name="Source", amount=Money("1000", EUR))
    _target, _target_id = budget_setup.a_budget(name="Target", amount=Money("1000", EUR))

    response = client.post(
        reverse("invoices:budget_transfer", kwargs={"pk": source_id}),
        {"target": str(_target_id), "amount": "abc", "provenance_note": ""},
    )

    assert response.status_code == 200
    from coda.apps.invoices.models import BudgetTransfer

    assert BudgetTransfer.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_create__duplicate_name__renders_error_and_persists_nothing(
    client: Client,
) -> None:
    budget_setup.a_budget(name="DARK 2026")

    response = client.post(
        reverse("invoices:fundingsource_create"),
        {
            "name": "DARK 2026",
            "budget_amount": "10000",
            "budget_currency": "EUR",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
        },
    )

    assert response.status_code == 200
    assert "already exists" in response.content.decode()
    from coda.apps.invoices.models import FundingSource

    assert FundingSource.objects.filter(name="DARK 2026").count() == 1


@pytest.mark.django_db
def test__budget_names_are_unique_among_budgets() -> None:
    from coda.apps.invoices import funding_source_repository
    from coda.domain.finance.funding_sources import Budget

    budget_setup.a_budget(name="DARK 2026")

    with pytest.raises(funding_source_repository.BudgetNameNotUnique):
        funding_source_repository.create(Budget.new("DARK 2026", amount=Money("1000", EUR)))


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_create__with_full_attributes__persists_budget(client: Client) -> None:
    from coda.apps.invoices.models import FundingSource

    response = client.post(
        reverse("invoices:fundingsource_create"),
        {
            "name": "DARK 2026",
            "budget_amount": "10000",
            "budget_currency": "EUR",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "allow_over": "on",
            "allowance_amount": "5000",
        },
    )

    assert response.status_code == 302
    budget = FundingSource.objects.get(name="DARK 2026")
    assert budget.budget_amount == Decimal(10000)
    assert budget.budget_currency == "EUR"
    assert str(budget.period_start) == "2026-01-01"
    assert str(budget.period_end) == "2026-12-31"
    assert budget.allow_over is True
    assert budget.allowance_amount == Decimal(5000)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_create__blank_terms__renders_field_errors_and_persists_nothing(
    client: Client,
) -> None:
    from coda.apps.invoices.models import FundingSource

    response = client.post(
        reverse("invoices:fundingsource_create"),
        {"name": "DARK 2026"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "required" in content
    assert not FundingSource.objects.filter(name="DARK 2026").exists()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_update__amount_after_period_start__cannot_be_changed(client: Client) -> None:
    _budget, budget_id = budget_setup.a_budget(name="DARK 2026", amount=Money("10000", EUR))

    response = client.post(
        reverse("invoices:fundingsource_update", kwargs={"pk": budget_id}),
        {
            "name": "DARK 2026",
            "budget_amount": "20000",
            "budget_currency": "EUR",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
        },
    )

    assert response.status_code == 302  # the crafted amount is ignored, not an error
    from coda.apps.invoices.models import FundingSource

    assert FundingSource.objects.get(pk=budget_id).budget_amount == Decimal(10000)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_update__amount_field_is_disabled_after_period_start(client: Client) -> None:
    _budget, budget_id = budget_setup.a_budget(name="DARK 2026", amount=Money("10000", EUR))

    response = client.get(reverse("invoices:fundingsource_update", kwargs={"pk": budget_id}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "disabled" in content
    assert "immutable once the period has started" in content


# --- Amendment — budget UI completion: cycle 1 (funding-source rendering) ---


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__funding_source__renders_as_name_in_selects(client: Client) -> None:
    """Funding sources render by name in the review-split select and the
    invoice filter sidebar — never as the model repr. An institution-type
    source falls back to its institution's label."""
    _budget, budget_id = budget_setup.a_budget(name="DARK 2026")
    institution = Institution.objects.create(name="Bielefeld University")
    institution_source = FundingSource.objects.create(type="institution", institution=institution)

    review_page = client.get(
        reverse("fundingrequests:review", kwargs={"pk": modelfactory.fundingrequest().pk})
    )
    review_html = review_page.content.decode()
    assert f'<option value="{budget_id}">DARK 2026</option>' in review_html
    assert "FundingSource object" not in review_html

    invoice_list_page = client.get(reverse("invoices:list"))
    list_html = invoice_list_page.content.decode()
    assert f'<option value="{budget_id}">DARK 2026</option>' in list_html
    assert "FundingSource object" not in list_html

    assert str(institution_source) == "Bielefeld University"
    assert str(FundingSource.objects.get(pk=budget_id)) == "DARK 2026"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_with_blank_name__renders_pk_label(client: Client) -> None:
    """A budget row with a blank name and no linked institution renders a
    pk-based label in the invoice filter sidebar instead of crashing."""
    budget = FundingSource.objects.create(
        type="budget",
        budget_amount=Decimal(1000),
        budget_currency="EUR",
        period_start="2026-01-01",
        period_end="2026-12-31",
    )

    response = client.get(reverse("invoices:list"))

    content = response.content.decode()
    assert f"FundingSource #{budget.pk}" in content
    assert "FundingSource object" not in content
    assert str(budget) == f"FundingSource #{budget.pk}"


# --- Amendment — budget UI completion: cycle 2 (detail balance overview) ---


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_detail__shows_available_figure_and_balance_bar(client: Client) -> None:
    """The detail page leads with a big available (gross-of-tax) figure beside
    a slim bar of spent (red) and reserved (amber) out of the amount; the
    secondary line states the amount (+ allowance) gross-of-tax."""
    budget, budget_id = budget_setup.a_budget(name="DARK 2026", amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("2500", EUR), budget, paid=True)
    budget_setup.an_invoice_with_assignment(Money("2000", EUR), budget, paid=False)
    row = FundingSource.objects.get(pk=budget_id)
    row.allow_over = True
    row.allowance_amount = Decimal(5000)
    row.save()

    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": budget_id}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Available (gross-of-tax)" in content
    assert "5500.00 EUR" in content  # available figure
    assert "budget-balance-bar" in content
    assert "budget-balance-bar__available" in content
    assert "width: calc(36.67% - 2.0px)" in content  # available segment (base fill)
    assert "budget-balance-bar__spent" in content
    assert "width: calc(16.67% - 2.0px)" in content  # 2500 of 10000 spent, block capped at amount + allowance
    assert "budget-balance-bar__reserved" in content
    assert "width: calc(13.33% - 2.0px)" in content  # 2000 of 10000 reserved
    assert "budget-balance-bar__over" not in content  # no over-segment within amount + allowance
    assert "of 10000.00 EUR gross-of-tax (+ 5000.0000 EUR allowance)" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_detail__zero_bookings__renders_full_available_bar(client: Client) -> None:
    """The bar is never invisible: zero bookings renders one full-width
    available segment (§8.1.1 base fill)."""
    budget, budget_id = budget_setup.a_budget(name="Fresh 2027", amount=Money("10000", EUR))

    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": budget_id}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "budget-balance-bar__available" in content
    assert "width: calc(100.00% - 0.0px)" in content  # full-width available base fill


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_detail__exceeded__shows_red_available_and_over_segment(client: Client) -> None:
    """An exceeded budget's available figure turns red; the bar renders a
    hatched over-segment inside the pill for the part beyond amount +
    allowance (reversing the earlier "no overfull segment" wording)."""
    budget, budget_id = budget_setup.a_budget(name="LibrOpenAPC", amount=Money("1000", EUR))
    row = FundingSource.objects.get(pk=budget_id)
    row.allowance_amount = Decimal(500)
    row.save()
    budget_setup.an_invoice_with_assignment(Money("1600", EUR), budget, paid=True)

    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": budget_id}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "budget-balance-figure danger" in content
    assert "-600.00 EUR" in content
    assert "budget-balance-bar__available" not in content  # available floored at 0
    assert "budget-balance-bar__reserved" not in content  # zero-width segments gated
    assert "budget-balance-bar__over" in content
    assert "width: calc(93.75% - 1.5px)" in content  # committed block capped at amount + allowance (1500/1600)
    assert "width: calc(6.25% - 1.5px)" in content  # hatched over-segment (100/1600)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_detail__shows_pending_conversion_annotation(client: Client) -> None:
    """Pending conversion is an annotation in the original currency — excluded
    from available — never a bar segment."""
    budget, budget_id = budget_setup.a_budget(name="Rate Pending", amount=Money("10000", EUR))
    budget_setup.an_invoice_with_assignment(Money("3000", USD), budget, paid=True)

    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": budget_id}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Pending conversion" in content
    assert "3000.00 USD" in content
    assert "excluded from available" in content
    assert "budget-balance-bar__pending" not in content


# --- Amendment — budget UI completion: cycle 3 (invoice reference list) ---


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_detail__lists_invoices_referencing_the_source(client: Client) -> None:
    """The detail page lists the invoices whose current funding assignments
    reference the source — the 10 most recent as invoice-number links to the
    invoice detail page, plus a deep link to the invoice list pre-filtered by
    this funding source. No date filtering: purely assignment-based."""
    budget, budget_id = budget_setup.a_budget(name="DARK 2026", amount=Money("100000", EUR))
    recent: list[tuple[str, int]] = []
    for i in range(10):
        invoice = budget_setup.an_unsaved_invoice_with_assignment(Money("10", EUR), budget)
        invoice.number = f"INV-RECENT-{i:02}"
        invoice.date = date(2026, 11, 1) - timedelta(days=i)
        recent.append((invoice.number, invoice_repository.create(invoice)))
    older = budget_setup.an_unsaved_invoice_with_assignment(Money("10", EUR), budget)
    older.number = "INV-OLDEST"
    older.date = date(2025, 1, 1)
    invoice_repository.create(older)

    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": budget_id}))

    assert response.status_code == 200
    content = response.content.decode()
    for number, pk in recent:
        assert f'<a href="{reverse("invoices:detail", kwargs={"pk": pk})}">{number}</a>' in content
    assert "INV-OLDEST" not in content  # 11th invoice, beyond the cap of 10
    assert f'href="{reverse("invoices:list")}?funding_source={budget_id}"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_detail__ignores_deleted_assignments(client: Client) -> None:
    """An invoice re-saved (positions and funding assignments recreated) must
    appear exactly once in the reference list: the save deletes the old
    assignment rows, and the list deduplicates the assignment join — two
    positions assigned to the same budget join twice without it."""
    from coda.domain.finance import invoice_positions
    from coda.domain.finance.costtypes import PublicationCostType
    from coda.domain.finance.invoice import CreditorId, InvoiceId, PaymentStatus
    from coda.domain.finance.invoice_positions import FreeItem
    from coda.domain.finance.taxrate import TaxRate
    from tests import domainfactory

    budget, budget_id = budget_setup.a_budget(name="DARK 2026", amount=Money("100000", EUR))
    positions = []
    for i in range(2):
        position = invoice_positions.create(
            item=FreeItem(f"APC {i}", cost_type=PublicationCostType.Gold_OA),
            cost=Money("10", EUR),
            tax_rate=TaxRate.from_percentage(0),
            external_position_id=f"POS-{i}",
        )
        position.assign_funding(budget, Decimal(10))
        positions.append(position)
    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk), positions=positions
    )
    invoice.status = PaymentStatus.Unpaid
    pk = invoice_repository.create(invoice)

    invoice.id = InvoiceId(pk)
    invoice.number = "INV-RESAVED"
    invoice_repository.update(invoice)  # re-save: positions/assignments recreated

    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": budget_id}))

    assert response.status_code == 200
    content = response.content.decode()
    link = f'<a href="{reverse("invoices:detail", kwargs={"pk": pk})}">INV-RESAVED</a>'
    assert content.count(link) == 1


# --- Amendment — budget UI completion: cycle 4 (list navigation) ---


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__budget_list__name_links_to_detail(client: Client) -> None:
    """The list row's name links to the detail page (house pattern, as the
    institutions list); Edit stays beside it."""
    _budget, budget_id = budget_setup.a_budget(name="DARK 2026")

    response = client.get(reverse("invoices:fundingsource_list"))

    assert response.status_code == 200
    content = response.content.decode()
    detail_url = reverse("invoices:fundingsource_detail", kwargs={"pk": budget_id})
    assert f'<a href="{detail_url}">DARK 2026</a>' in content
    edit_url = reverse("invoices:fundingsource_update", kwargs={"pk": budget_id})
    assert edit_url in content
    assert ">Edit</a>" in content


# --- Amendment — budget UI completion: cycle 5 (institution routes) ---


def _institution_source_with(*, institution: Institution | None) -> FundingSource:
    return FundingSource.objects.create(type="institution", institution=institution)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__institution_source__detail_redirects_to_institution_page(client: Client) -> None:
    """Institution-type funding sources have no detail page: both a linked
    and a soft-deleted institution resolve to the institution's detail page;
    a missing FK falls back to the institution list."""
    institution = Institution.objects.create(name="Bielefeld University")
    source = _institution_source_with(institution=institution)
    deleted = Institution.objects.create(name="Gone University")
    deleted_source = _institution_source_with(institution=deleted)
    orphan = _institution_source_with(institution=None)

    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": source.pk}))
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("institutions:detail", kwargs={"pk": institution.pk})

    deleted.archive()
    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": deleted_source.pk}))
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("institutions:detail", kwargs={"pk": deleted.pk})

    response = client.get(reverse("invoices:fundingsource_detail", kwargs={"pk": orphan.pk}))
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("institutions:list")


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__institution_source__update_redirects_to_institution_page(client: Client) -> None:
    """Institution-type funding sources are not editable: the update route
    redirects to the linked institution (soft-deleted ones still resolve);
    a missing FK falls back to the institution list."""
    institution = Institution.objects.create(name="Bielefeld University")
    source = _institution_source_with(institution=institution)
    deleted = Institution.objects.create(name="Gone University")
    deleted_source = _institution_source_with(institution=deleted)
    orphan = _institution_source_with(institution=None)

    response = client.get(reverse("invoices:fundingsource_update", kwargs={"pk": source.pk}))
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("institutions:detail", kwargs={"pk": institution.pk})

    deleted.archive()
    response = client.get(reverse("invoices:fundingsource_update", kwargs={"pk": deleted_source.pk}))
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("institutions:detail", kwargs={"pk": deleted.pk})

    response = client.get(reverse("invoices:fundingsource_update", kwargs={"pk": orphan.pk}))
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("institutions:list")
