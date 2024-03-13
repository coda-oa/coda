from typing import Any, cast

import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests.services import label_attach, label_create
from coda.apps.fundingrequests.views import FundingRequestListView
from coda.color import Color
from tests.fundingrequests.test_fundingrequest_labels import logged_in  # noqa: F401
from tests.fundingrequests.test_fundingrequest_repository import fundingrequest


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests__shows_all_funding_requests(client: Client) -> None:
    requests = {fundingrequest(), fundingrequest()}

    response = fundingrequest_list(client)

    assert set(response.context[FundingRequestListView.context_object_name]) == requests


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_title__shows_only_matching_funding_requests(
    client: Client,
) -> None:
    title = "The Search Term"
    matching_request = fundingrequest(title)

    _ = fundingrequest("No match")

    response = fundingrequest_list(client, {"title": title})

    assert list(response.context[FundingRequestListView.context_object_name]) == [matching_request]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_label__shows_only_matching_funding_requests(
    client: Client,
) -> None:
    matching_request = fundingrequest()
    first = label_create("The Label", Color())
    label_attach(matching_request.pk, first.pk)
    second = label_create("Another Label", Color())
    label_attach(matching_request.pk, second.pk)

    _ = fundingrequest("No match")

    response = fundingrequest_list(client, {"labels": [first.pk, second.pk]})

    assert list(response.context[FundingRequestListView.context_object_name]) == [matching_request]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__searching_for_funding_requests_by_process_state__shows_only_matching_funding_requests(
    client: Client,
) -> None:
    approved_request = fundingrequest()
    approved_request.approve()

    rejected_request = fundingrequest()
    rejected_request.reject()

    in_progress_request = fundingrequest()  # noqa: F841

    query = {"processing_status": ["approved", "rejected"]}
    response = fundingrequest_list(client, query)

    rendered_requests = response.context[FundingRequestListView.context_object_name]
    assert set(rendered_requests) == {approved_request, rejected_request}


def fundingrequest_list(client: Client, query: dict[str, Any] | None = None) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("fundingrequests:list"), data=query))
