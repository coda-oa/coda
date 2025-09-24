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
        reverse("fundingrequests:review_submit", kwargs={"pk": fr_id}),
        {
            "action": "approve",
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
        reverse("fundingrequests:review_submit", kwargs={"pk": fr_id}),
        {
            "action": "reject",
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
        reverse("fundingrequests:review_submit", kwargs={"pk": fr_id}),
        {
            "action": "waive",
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
        reverse("fundingrequests:review_submit", kwargs={"pk": fr_id}),
        {
            "action": "close",
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
        reverse("fundingrequests:review_submit", kwargs={"pk": fr.id}),
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


def fundingrequest() -> FundingRequest[Publication]:
    journal_id = JournalId(modelfactory.journal().pk)
    organization_id = FundingOrganizationId(modelfactory.funding_organization().pk)
    return domainfactory.fundingrequest(journal_id=journal_id, funding_org_id=organization_id)
