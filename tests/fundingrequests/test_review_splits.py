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
