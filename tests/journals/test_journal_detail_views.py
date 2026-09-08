import pytest
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.journals.models import Journal
from tests import modelfactory


def _detail_url(journal: Journal) -> str:
    return reverse("publishing:journals:detail", kwargs={"eissn": journal.eissn})


def _fundingrequest_for(journal: Journal, title: str) -> FundingRequest:
    funding_request = modelfactory.fundingrequest(title=title)
    funding_request.publication.article_journal = journal
    funding_request.publication.save()
    return funding_request


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_detail__lists_related_funding_requests(client: Client) -> None:
    journal = modelfactory.journal(title="Journal of Testing")
    funding_request = _fundingrequest_for(journal, "Testing Patterns")

    response = client.get(_detail_url(journal))
    content = response.content.decode()

    assert funding_request.request_id in content
    assert "Testing Patterns" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_detail__excludes_funding_requests_of_other_journals(client: Client) -> None:
    journal = modelfactory.journal(title="Journal of Testing")
    other_journal = modelfactory.journal(title="Journal of Impostors")
    foreign = _fundingrequest_for(other_journal, "Foreign Publication")
    own = _fundingrequest_for(journal, "Own Publication")

    response = client.get(_detail_url(journal))
    content = response.content.decode()

    assert own.request_id in content
    assert foreign.request_id not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_detail__no_funding_requests_shows_placeholder(client: Client) -> None:
    journal = modelfactory.journal(title="Lonely Journal")

    response = client.get(_detail_url(journal))

    assert "No related funding requests." in response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__journal_detail__funding_requests_ordered_by_request_date_desc(client: Client) -> None:
    journal = modelfactory.journal(title="Journal of Testing")
    first = _fundingrequest_for(journal, "First")
    second = _fundingrequest_for(journal, "Second")

    first_date = first.request_date.replace(year=2020)
    second_date = second.request_date.replace(year=2021)
    FundingRequest.objects.filter(pk=first.pk).update(request_date=first_date)
    FundingRequest.objects.filter(pk=second.pk).update(request_date=second_date)

    response = client.get(_detail_url(journal))

    listed_ids = [fr.request_id for fr in response.context["funding_requests"]]
    assert listed_ids == [second.request_id, first.request_id]
