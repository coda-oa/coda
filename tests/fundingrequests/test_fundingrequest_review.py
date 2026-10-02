import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests import repository
from coda.domain.fundingrequest import Review
from coda.domain.fundingrequest import FundingOrganizationId, FundingRequest
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.money import Currency, Money
from coda.domain.publication import JournalId, Publication
from tests import domainfactory, modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest__approving_with_funding_amount_and_remarks__stores_in_database(
    client: Client,
) -> None:
    fr = fundingrequest()
    fr_id = repository.create(fr)
    funding = Money(100, Currency.EUR)
    remarks = "Approved with funding"

    client.post(
        reverse("fundingrequests:review", kwargs={"pk": fr_id}),
        {
            "action": "approved",
            "decided_funding_amount": funding.amount,
            "decided_funding_currency": funding.currency.code,
            "reviewer_remarks": remarks,
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
