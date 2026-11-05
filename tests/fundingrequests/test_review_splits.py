import re
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.invoices import budget_query
from coda.contexts.finance.services import budget_service
from coda.contexts.fundingrequest.dto.commands import ReviewSplitDto, UpdateReviewDto
from coda.contexts.fundingrequest.services import fundingrequests as services
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.money import Currency, Money
from tests import modelfactory
from tests.invoices import budget_setup

EUR = Currency.EUR


def _split_dto(budget_id: int, amount: Decimal) -> ReviewSplitDto:
    return ReviewSplitDto(funding_source_id=budget_id, amount=amount)


def _approve_dto(budget_id: int, amount: Decimal) -> UpdateReviewDto:
    return UpdateReviewDto(
        decided_funding_amount=amount,
        decided_funding_currency="EUR",
        reviewer_remarks="",
        result="approved",
        funding_splits=[_split_dto(budget_id, amount)],
    )


@pytest.mark.django_db
def test__re_approval__does_not_double_count_own_splits() -> None:
    """Re-submitting an approved review unchanged must not double-count its
    own persisted splits: budget 1 000, own split 600, re-submit → accepted."""
    _budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()

    services.update_review(FundingRequestId(funding_request.pk), _approve_dto(budget_id, Decimal(600)))
    services.update_review(FundingRequestId(funding_request.pk), _approve_dto(budget_id, Decimal(600)))

    assert budget_query.budget_balances(budget_id).reserved == Money("600", EUR)


@pytest.mark.django_db
def test__re_approval__raised_split_beyond_remaining__rejected() -> None:
    _budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()

    services.update_review(FundingRequestId(funding_request.pk), _approve_dto(budget_id, Decimal(600)))
    services.update_review(FundingRequestId(funding_request.pk), _approve_dto(budget_id, Decimal(900)))

    with pytest.raises(budget_service.BudgetCapacityExceededError):
        services.update_review(
            FundingRequestId(funding_request.pk), _approve_dto(budget_id, Decimal(1100))
        )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__refresh_round_trips(client: Client) -> None:
    """The form_action_refresh marker re-renders the page with recomputed
    feedback and the entered data — without saving anything."""
    _budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}),
        {
            "decided_funding_amount": "600",
            "decided_funding_currency": "EUR",
            "reviewer_remarks": "",
            "action": "return",
            "form_action_refresh": "1",
            "funding_splits-TOTAL_FORMS": "1",
            "funding_splits-INITIAL_FORMS": "0",
            "funding_splits-0-funding_source": str(budget_id),
            "funding_splits-0-amount": "600",
        },
    )

    assert response.status_code == 200
    rows = response.context["split_rows"]
    assert rows[0]["gross_left"] == Money("400", EUR)  # 1 000 − 600, recomputed
    assert rows[0]["feedback"] == "fits"
    # Nothing saved: the review is still open, no splits persisted.
    funding_request.refresh_from_db()
    assert funding_request.review.review_result == "open"
    assert funding_request.review.funding_splits.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__refresh_aggregates_sibling_rows(client: Client) -> None:
    """Two rows on one budget aggregate into one gross-left figure on the
    live path (the sibling constraint, pinned on the refresh POST)."""
    _budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}),
        {
            "decided_funding_amount": "1200",
            "decided_funding_currency": "EUR",
            "reviewer_remarks": "",
            "action": "return",
            "form_action_refresh": "1",
            "funding_splits-TOTAL_FORMS": "2",
            "funding_splits-INITIAL_FORMS": "0",
            "funding_splits-0-funding_source": str(budget_id),
            "funding_splits-0-amount": "600",
            "funding_splits-1-funding_source": str(budget_id),
            "funding_splits-1-amount": "600",
        },
    )

    assert response.status_code == 200
    rows = response.context["split_rows"]
    assert rows[0]["gross_left"] == Money("-200", EUR)  # aggregated, not per-row
    assert "exceeds" in rows[0]["feedback"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__split_inputs_carry_live_refresh_attrs(client: Client) -> None:
    """The htmx wiring is the half the tests can't exercise (no JS): pin the
    rendered attributes — the delegation div's POST/trigger/include and the
    refresh marker — so a template regression can't silently kill live fit."""
    _budget, _budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()

    response = client.get(reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}))

    content = response.content.decode()
    assert f'hx-post="{reverse("fundingrequests:review", kwargs={"pk": funding_request.pk})}"' in content
    assert 'hx-trigger="change from:#split-table"' in content
    assert 'hx-include="closest form"' in content
    assert '{"form_action_refresh": "1"}' in content
    assert 'id="split-table"' in content
    assert "htmx" in content  # htmx itself is loaded (base: {% htmx_script %})


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__no_available_per_budget_list(client: Client) -> None:
    _budget, _budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()

    response = client.get(reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}))

    assert b"Available per budget" not in response.content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__prefills_persisted_splits(client: Client) -> None:
    """Re-opening an approved review renders the persisted splits as filled
    rows (plus the extra blank row) with their gross-left figures and the sum
    verdict — not blank inputs."""
    _budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()
    services.update_review(FundingRequestId(funding_request.pk), _approve_dto(budget_id, Decimal(600)))

    response = client.get(reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}))

    formset = response.context["funding_splits"]
    assert formset.total_form_count() == 2  # persisted + extra=1 blank
    assert int(formset.forms[0].initial["funding_source"]) == budget_id
    assert Decimal(formset.forms[0].initial["amount"]) == Decimal(600)
    content = response.content.decode()
    assert "600.00" in content  # the persisted amount renders
    assert "fits" in content  # the unchanged row fits (delta 0 over own totals)
    assert "exceeds" not in content  # no false over figure on an unchanged re-open
    # The row's gross-left figure agrees with the own-excluded budgets list
    # (both on the same basis): 1 000, not the double-counted 400.
    rows = response.context["split_rows"]
    assert rows[0]["gross_left"] == Money("1000", EUR)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__prefilled_gross_left_after_raise(client: Client) -> None:
    """Re-approving with a raised split (600 → 900) then re-opening: the row's
    gross-left figure is on the own-excluded basis (1 000), matching the
    budgets list."""
    _budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()
    services.update_review(FundingRequestId(funding_request.pk), _approve_dto(budget_id, Decimal(600)))
    services.update_review(FundingRequestId(funding_request.pk), _approve_dto(budget_id, Decimal(900)))

    response = client.get(reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}))

    rows = response.context["split_rows"]
    assert rows[0]["gross_left"] == Money("1000", EUR)
    assert rows[0]["feedback"] == "fits"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__available_excludes_own_persisted_splits(client: Client) -> None:
    """The review page's per-budget available excludes the review's own
    persisted splits (the capacity the reviewer is actually deciding against)."""
    _budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()
    services.update_review(FundingRequestId(funding_request.pk), _approve_dto(budget_id, Decimal(600)))

    response = client.get(reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}))

    budgets = response.context["budgets"]
    own = next(b for b in budgets if b["id"] == str(budget_id))
    assert own["available"] == Money("1000", EUR)


@pytest.mark.django_db
def test__waived_review__reserves_nothing() -> None:
    """A waived review persists no funding splits even when split data is
    submitted — the guard is a single conditional in update_review; this pins
    it against silent budget reservation."""
    _budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    services.update_review(
        FundingRequestId(funding_request.pk),
        UpdateReviewDto(
            decided_funding_amount=Decimal(2000),
            decided_funding_currency="EUR",
            reviewer_remarks="",
            result="waived",
            funding_splits=[ReviewSplitDto(funding_source_id=budget_id, amount=Decimal(2000))],
        ),
    )

    assert funding_request.review.funding_splits.count() == 0
    assert budget_query.budget_balances(budget_id).reserved == Money("0", EUR)


@pytest.mark.django_db
def test__approving_review_with_valid_split__persists_split_and_reserves_budget() -> None:
    _budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    services.update_review(
        FundingRequestId(funding_request.pk),
        UpdateReviewDto(
            decided_funding_amount=Decimal(2000),
            decided_funding_currency="EUR",
            reviewer_remarks="",
            result="approved",
            funding_splits=[ReviewSplitDto(funding_source_id=budget_id, amount=Decimal(2000))],
        ),
    )

    funding_request.refresh_from_db()
    split = funding_request.review.funding_splits.get()
    assert split.funding_source_id == budget_id
    assert split.amount == Decimal(2000)

    balance = budget_query.budget_balances(budget_id)
    assert balance.reserved == Money("2000", EUR)
    assert balance.available == Money("8000", EUR)


@pytest.mark.django_db
def test__review_splits_not_summing_to_decided_funding__rejected() -> None:
    _budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    with pytest.raises(services.InvalidFundingSplit):
        services.update_review(
            FundingRequestId(funding_request.pk),
            UpdateReviewDto(
                decided_funding_amount=Decimal(2000),
                decided_funding_currency="EUR",
                reviewer_remarks="",
                result="approved",
                funding_splits=[ReviewSplitDto(funding_source_id=budget_id, amount=Decimal(1500))],
            ),
        )

    funding_request.refresh_from_db()
    assert funding_request.review.funding_splits.count() == 0
    assert budget_query.budget_balances(budget_id).reserved == Money("0", EUR)


@pytest.mark.django_db
def test__approving_review_without_splits__rejected() -> None:
    _budget, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    with pytest.raises(services.InvalidFundingSplit):
        services.update_review(
            FundingRequestId(funding_request.pk),
            UpdateReviewDto(
                decided_funding_amount=Decimal(2000),
                decided_funding_currency="EUR",
                reviewer_remarks="",
                result="approved",
                funding_splits=[],
            ),
        )

    funding_request.refresh_from_db()
    assert funding_request.review.funding_splits.count() == 0
    assert budget_query.budget_balances(budget_id).reserved == Money("0", EUR)


@pytest.mark.django_db
def test__approving_review_zero_decided_funding_without_splits__valid() -> None:
    funding_request = modelfactory.fundingrequest()

    services.update_review(
        FundingRequestId(funding_request.pk),
        UpdateReviewDto(
            decided_funding_amount=Decimal(0),
            decided_funding_currency="EUR",
            reviewer_remarks="",
            result="approved",
            funding_splits=[],
        ),
    )

    funding_request.refresh_from_db()
    assert funding_request.review.funding_splits.count() == 0


@pytest.mark.django_db
def test__review_splits_on_same_budget_aggregated_for_capacity__rejected() -> None:
    """Two splits on the same budget must be capacity-checked against their
    sum, not individually — two 600 EUR splits do not fit a 1000 EUR budget."""
    _budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()

    with pytest.raises(budget_service.BudgetCapacityExceededError):
        services.update_review(
            FundingRequestId(funding_request.pk),
            UpdateReviewDto(
                decided_funding_amount=Decimal(1200),
                decided_funding_currency="EUR",
                reviewer_remarks="",
                result="approved",
                funding_splits=[
                    ReviewSplitDto(funding_source_id=budget_id, amount=Decimal(600)),
                    ReviewSplitDto(funding_source_id=budget_id, amount=Decimal(600)),
                ],
            ),
        )

    funding_request.refresh_from_db()
    assert funding_request.review.funding_splits.count() == 0
    assert budget_query.budget_balances(budget_id).reserved == Money("0", EUR)


@pytest.mark.django_db
def test__review_split_exceeding_budget_capacity__rejected() -> None:
    _budget, budget_id = budget_setup.a_budget(amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()

    with pytest.raises(budget_service.BudgetCapacityExceededError):
        services.update_review(
            FundingRequestId(funding_request.pk),
            UpdateReviewDto(
                decided_funding_amount=Decimal(2000),
                decided_funding_currency="EUR",
                reviewer_remarks="",
                result="approved",
                funding_splits=[ReviewSplitDto(funding_source_id=budget_id, amount=Decimal(2000))],
            ),
        )

    funding_request.refresh_from_db()
    assert funding_request.review.funding_splits.count() == 0
    assert budget_query.budget_balances(budget_id).reserved == Money("0", EUR)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_view__approving_with_split__persists_split_and_reserves_budget(
    client: Client,
) -> None:
    _, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}),
        {
            "action": "approved",
            "decided_funding_amount": "2000",
            "decided_funding_currency": "EUR",
            "reviewer_remarks": "",
            "funding_splits-TOTAL_FORMS": "1",
            "funding_splits-INITIAL_FORMS": "0",
            "funding_splits-0-funding_source": str(budget_id),
            "funding_splits-0-amount": "2000",
        },
    )

    assert response.status_code == 302
    funding_request.refresh_from_db()
    split = funding_request.review.funding_splits.get()
    assert split.funding_source_id == budget_id
    assert budget_query.budget_balances(budget_id).reserved == Money("2000", EUR)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_view__split_exceeding_capacity__renders_error_and_blocks_approval(
    client: Client,
) -> None:
    _, budget_id = budget_setup.a_budget(name="Small Budget", amount=Money("1000", EUR))
    funding_request = modelfactory.fundingrequest()

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}),
        {
            "action": "approved",
            "decided_funding_amount": "2000",
            "decided_funding_currency": "EUR",
            "reviewer_remarks": "",
            "funding_splits-TOTAL_FORMS": "1",
            "funding_splits-INITIAL_FORMS": "0",
            "funding_splits-0-funding_source": str(budget_id),
            "funding_splits-0-amount": "2000",
        },
    )

    assert response.status_code == 200
    assert b"exceeds its capacity" in response.content
    funding_request.refresh_from_db()
    assert funding_request.review.review_result == "open"
    assert funding_request.review.funding_splits.count() == 0


def _input_value(content: str, name: str) -> str | None:
    for tag in re.findall(r"<input\b[^>]*>", content):
        if f'name="{name}"' in tag:
            match = re.search(r'value="([^"]*)"', tag)
            return match.group(1) if match else ""
    return None


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__renders_split_table_with_add_button(client: Client) -> None:
    budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    response = client.get(reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}))

    content = response.content.decode()
    assert 'name="form_action_add"' in content
    assert "+ Add funding source" in content
    assert "Funding source" in content
    assert "Amount (gross-of-tax)" in content
    assert "Gross left (all splits)" in content
    assert 'name="form_action_remove"' in content
    assert _input_value(content, "funding_splits-TOTAL_FORMS") == "1"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__add_row_round_trips(client: Client) -> None:
    _, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}),
        {
            "form_action_add": "add_form",
            "decided_funding_amount": "2000",
            "decided_funding_currency": "EUR",
            "reviewer_remarks": "",
            "funding_splits-TOTAL_FORMS": "1",
            "funding_splits-INITIAL_FORMS": "0",
            "funding_splits-0-funding_source": str(budget_id),
            "funding_splits-0-amount": "2000",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert _input_value(content, "funding_splits-TOTAL_FORMS") == "2"
    assert _input_value(content, "funding_splits-0-amount") == "2000"
    assert _input_value(content, "funding_splits-1-amount") == ""
    assert f'<option value="{budget_id}" selected' in content
    funding_request.refresh_from_db()
    assert funding_request.review.review_result == "open"
    assert funding_request.review.funding_splits.count() == 0


def _split_table_rows(content: str) -> list[str]:
    """The review page's split-table rows, in formset order."""
    return [
        row
        for row in re.findall(r"<tr>.*?</tr>", content, re.DOTALL)
        if "funding_splits-" in row
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__capacity_feedback_is_gross_of_tax_qualified(client: Client) -> None:
    _, a_id = budget_setup.a_budget(name="Budget A", amount=Money("1000", EUR))
    _, b_id = budget_setup.a_budget(name="Budget B", amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}),
        {
            "form_action_add": "add_form",
            "decided_funding_amount": "1700",
            "decided_funding_currency": "EUR",
            "reviewer_remarks": "",
            "funding_splits-TOTAL_FORMS": "3",
            "funding_splits-INITIAL_FORMS": "0",
            "funding_splits-0-funding_source": str(a_id),
            "funding_splits-0-amount": "600",
            "funding_splits-1-funding_source": str(a_id),
            "funding_splits-1-amount": "600",
            "funding_splits-2-funding_source": str(b_id),
            "funding_splits-2-amount": "500",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    budget_a_rows = [row for row in _split_table_rows(content) if f'value="{a_id}" selected' in row]
    budget_b_rows = [row for row in _split_table_rows(content) if f'value="{b_id}" selected' in row]
    assert len(budget_a_rows) == 2
    assert len(budget_b_rows) == 1
    # Both Budget A rows fit individually (600 ≤ 1000), but the sibling-
    # aggregated 1200 exceeds the budget's available 1000: each row shows the
    # aggregated gross-left figure (-200), not its single-row remainder (400).
    for row in budget_a_rows:
        assert re.search(r"-200\.00 EUR\s*<small>exceeds", row)
        assert "exceeds: only -200.00 EUR gross-of-tax available, over-budget not allowed" in row
        assert "400.00 EUR" not in row
    # Budget B (row index 2) is the row whose verdict is "fits": 500 of 10000.
    assert re.search(r"9500\.00 EUR\s*<small>fits", budget_b_rows[0])


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__sum_verdict_shows_difference(client: Client) -> None:
    _, budget_id = budget_setup.a_budget(amount=Money("10000", EUR))
    funding_request = modelfactory.fundingrequest()

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": funding_request.pk}),
        {
            "action": "approved",
            "decided_funding_amount": "2000",
            "decided_funding_currency": "EUR",
            "reviewer_remarks": "",
            "funding_splits-TOTAL_FORMS": "1",
            "funding_splits-INITIAL_FORMS": "0",
            "funding_splits-0-funding_source": str(budget_id),
            "funding_splits-0-amount": "1500",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "difference 500.00" in content
    assert "matches the decided amount" not in content
