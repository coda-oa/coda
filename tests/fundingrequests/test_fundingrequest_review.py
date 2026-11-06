from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests import repository
from coda.contexts.fundingrequest.dto.commands import ReviewSplitDto, UpdateReviewDto
from coda.contexts.fundingrequest.services import fundingrequests as fr_services
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest import (
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    Review,
)
from coda.domain.fundingrequest.review import FundingSplits, ReviewResult, ReviewSplit
from coda.domain.money import Currency, Money
from coda.domain.publication import JournalId, Publication
from tests import domainfactory, modelfactory
from tests.invoices import budget_setup


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest__approving_with_funding_amount_and_remarks__stores_in_database(
    client: Client,
) -> None:
    fr = fundingrequest()
    fr_id = repository.create(fr)
    funding = Money(100, Currency.EUR)
    remarks = "Approved with funding"
    _budget, budget_id = budget_setup.a_budget(amount=Money("10000", Currency.EUR))

    client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr_id}),
        {
            "action": "approved",
            "decided_funding_amount": funding.amount,
            "decided_funding_currency": funding.currency.code,
            "reviewer_remarks": remarks,
            "funding_splits-TOTAL_FORMS": "1",
            "funding_splits-INITIAL_FORMS": "0",
            "funding_splits-0-funding_source": str(budget_id),
            "funding_splits-0-amount": "100",
        },
    )

    actual = repository.get_by_id(fr_id)
    assert actual.review() == ReviewResult.Approved
    assert actual.funding_amount == funding
    assert actual.review_remarks == remarks


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest__rejecting_with_remark__stores_in_database(client: Client) -> None:
    fr = fundingrequest()
    fr_id = repository.create(fr)
    remarks = "Rejected because of reasons"

    client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr_id}),
        {
            "action": "rejected",
            "reviewer_remarks": remarks,
            "decided_funding_amount": 0,
            "decided_funding_currency": "EUR",
        },
    )

    actual = repository.get_by_id(fr_id)
    assert actual.review() == ReviewResult.Rejected
    assert actual.review_remarks == remarks
    assert actual.funding_amount == Money(0, Currency.EUR)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest__waive_costs__stores_in_database(client: Client) -> None:
    fr = fundingrequest()
    fr_id = repository.create(fr)
    remarks = "Waived costs"

    client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr_id}),
        {
            "action": "waived",
            "reviewer_remarks": remarks,
            "decided_funding_amount": 0,
            "decided_funding_currency": "EUR",
        },
    )

    actual = repository.get_by_id(fr_id)
    assert actual.costs_waived()
    assert actual.review_remarks == remarks


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest__close__stores_in_database(client: Client) -> None:
    fr = fundingrequest()
    fr_id = repository.create(fr)
    remarks = "Withdrawn"

    client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr_id}),
        {
            "action": "closed",
            "reviewer_remarks": remarks,
            "decided_funding_amount": 0,
            "decided_funding_currency": "EUR",
        },
    )

    actual = repository.get_by_id(fr_id)
    assert not actual.is_open()
    assert actual.review_remarks == remarks


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__closed_fundingrequest__re_opening__stores_in_database(client: Client) -> None:
    fr = fundingrequest()
    fr.id = repository.create(fr)
    review = Review(fr.id).update_review(ReviewResult.Open)
    repository.save_review(review)

    remarks = "Re-opened for further review"

    client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr.id}),
        {
            "action": "open",
            "reviewer_remarks": remarks,
            "decided_funding_amount": 0,
            "decided_funding_currency": "EUR",
        },
    )

    actual = repository.get_by_id(fr.id)
    assert actual.review() == ReviewResult.Open
    assert actual.review_remarks == remarks


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__action_return__updates_without_changing_result(client: Client) -> None:
    fr = fundingrequest()
    fr.id = repository.create(fr)
    review = Review(fr.id).update_review(ReviewResult.Approved)
    repository.save_review(review)

    remarks = "Some new remarks"

    client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr.id}),
        {
            "action": "return",
            "reviewer_remarks": remarks,
            "decided_funding_amount": 0,
            "decided_funding_currency": "EUR",
        },
    )

    actual = repository.get_by_id(fr.id)
    assert actual.review() == ReviewResult.Approved
    assert actual.review_remarks == remarks


@pytest.mark.parametrize(
    ("field", "bad_value", "expected_error"),
    [
        pytest.param("decided_funding_amount", "not-a-number", "Enter a number."),
        pytest.param("decided_funding_amount", "-5", "greater than or equal to 0"),
        pytest.param("decided_funding_currency", "XYZ", "Select a valid choice"),
        pytest.param("action", "self-approve", "Select a valid choice"),
    ],
)
@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_submit__invalid_input__re_renders_form_and_stores_nothing(
    client: Client, field: str, bad_value: str, expected_error: str
) -> None:
    fr = fundingrequest()
    fr.id = repository.create(fr)
    before = repository.get_by_id(fr.id)

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr.id}),
        {
            "action": "approved",
            "decided_funding_amount": "100.00",
            "decided_funding_currency": "EUR",
            "reviewer_remarks": "keep me",
            field: bad_value,
        },
    )

    assert response.status_code == 200
    assert expected_error in response.content.decode()
    actual = repository.get_by_id(fr.id)
    assert actual.review() == before.review()
    assert actual.funding_amount == before.funding_amount
    assert actual.review_remarks == before.review_remarks


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_submit__split_in_foreign_currency__renders_error_and_stores_nothing(
    client: Client,
) -> None:
    """Splits are counted in the budget's currency: a split decided in a
    foreign currency is rejected on save — and the re-rendered preview shows
    the currency reason instead of crashing on a cross-currency comparison."""
    fr = fundingrequest()
    fr.id = repository.create(fr)
    _budget, budget_id = budget_setup.a_budget(amount=Money("5000", Currency.SEK))

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr.id}),
        {
            "action": "approved",
            "decided_funding_amount": "100",
            "decided_funding_currency": "EUR",
            "reviewer_remarks": "",
            "funding_splits-TOTAL_FORMS": "1",
            "funding_splits-INITIAL_FORMS": "0",
            "funding_splits-0-funding_source": str(budget_id),
            "funding_splits-0-amount": "100",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    # The message renders twice: once as the save's form error and once as
    # the preview row's feedback — pinning both surfaces, not just one.
    assert content.count("denominated in SEK") == 2
    actual = repository.get_by_id(fr.id)
    assert actual.review() == ReviewResult.Open


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_preview__posted_currency_matching_budget__shows_no_mismatch(
    client: Client,
) -> None:
    """The preview judges the *posted* decided currency — the one save
    validates against: a SEK-decided split on a SEK budget renders a capacity
    verdict, not a currency mismatch, even though the FR was funded in EUR."""
    fr = fundingrequest()
    fr.id = repository.create(fr)
    _budget, budget_id = budget_setup.a_budget(amount=Money("5000", Currency.SEK))

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr.id}),
        {
            # Blank amount forces form_invalid → the preview re-renders with
            # the posted split data.
            "action": "approved",
            "decided_funding_amount": "",
            "decided_funding_currency": "SEK",
            "reviewer_remarks": "",
            "funding_splits-TOTAL_FORMS": "1",
            "funding_splits-INITIAL_FORMS": "0",
            "funding_splits-0-funding_source": str(budget_id),
            "funding_splits-0-amount": "100",
        },
    )

    assert response.status_code == 200
    assert "denominated in SEK" not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_preview__decided_currency_changed__flags_stale_splits(client: Client) -> None:
    """A currency change voids the persisted splits: the preview flags them
    instead of exempting them from the capacity verdict — matching the save's
    rejection instead of showing capacity room the save will refuse."""
    fr = fundingrequest()
    fr.id = repository.create(fr)
    _budget, budget_id = budget_setup.a_budget(amount=Money("5000", Currency.EUR))

    repository.save_review(
        Review(FundingRequestId(fr.id)).update_review(
            ReviewResult.Approved,
            Money("1000", Currency.SEK),
            funding_splits=FundingSplits.of(
                [ReviewSplit(FundingSourceId(budget_id), Money("1000", Currency.SEK))]
            ),
        )
    )

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr.id}),
        {
            "action": "approved",
            "decided_funding_amount": "",
            "decided_funding_currency": "EUR",
            "reviewer_remarks": "",
            "funding_splits-TOTAL_FORMS": "1",
            "funding_splits-INITIAL_FORMS": "0",
            "funding_splits-0-funding_source": str(budget_id),
            "funding_splits-0-amount": "1000",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "belong to the old decision" in content
    assert "fits" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_page__legacy_foreign_currency_split__renders_currency_reason(
    client: Client,
) -> None:
    """Datasets created before the save guard can hold a split whose decided
    currency differs from the FR's funding currency. Re-opening that review
    must render the currency reason — not crash on a cross-currency
    comparison."""
    fr = fundingrequest()
    fr.id = repository.create(fr)
    _budget, budget_id = budget_setup.a_budget(amount=Money("5000", Currency.SEK))

    # Approve with a SEK-decided split (valid: matches the budget's currency),
    # then rewind the review's decided funding to EUR — the legacy
    # inconsistency the save guard now prevents.
    fr_services.update_review(
        FundingRequestId(fr.id),
        UpdateReviewDto(
            decided_funding_amount=Decimal(1000),
            decided_funding_currency="SEK",
            reviewer_remarks="",
            result="approved",
            funding_splits=[ReviewSplitDto(funding_source_id=budget_id, amount=Decimal(1000))],
        ),
    )
    from coda.apps.fundingrequests.models import FundingRequestReview

    FundingRequestReview.objects.filter(fundingrequest=fr.id).update(
        decided_funding_amount=Decimal(100), decided_funding_currency="EUR"
    )

    response = client.get(reverse("fundingrequests:review", kwargs={"pk": fr.id}))

    assert response.status_code == 200
    assert "denominated in SEK" in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__review_submit__missing_action__re_renders_form_with_error(client: Client) -> None:
    fr = fundingrequest()
    fr.id = repository.create(fr)

    response = client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr.id}),
        {
            "decided_funding_amount": "100.00",
            "decided_funding_currency": "EUR",
            "reviewer_remarks": "keep me",
        },
    )

    assert response.status_code == 200
    assert "This field is required" in response.content.decode()
    assert repository.get_by_id(fr.id).review_remarks == ""


def fundingrequest() -> FundingRequest[Publication]:
    journal_id = JournalId(modelfactory.journal().pk)
    organization_id = FundingOrganizationId(modelfactory.funding_organization().pk)
    return domainfactory.fundingrequest(journal_id=journal_id, funding_org_id=organization_id)
