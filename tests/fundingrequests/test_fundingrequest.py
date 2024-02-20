import datetime
from django.test import Client

import pytest

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.institutions.models import Institution
from coda.apps.journals.models import Journal
from coda.apps.publications.models import Publication
from coda.apps.publishers.models import Publisher


def publisher() -> Publisher:
    return Publisher.objects.create(name="Test Publisher")


def publication() -> Publication:
    return Publication.objects.create(
        title="Test Publication",
        journal=Journal.objects.create(
            title="Test Journal", eissn="1234-5678", publisher=publisher()
        ),
    )


@pytest.mark.django_db
def test__fundingrequest__has_valid_id_pattern() -> None:
    request = FundingRequest.objects.create(
        publication=publication(), estimated_cost=100, estimated_cost_currency="USD"
    )

    split_id = request.request_id.split("-")
    uuid_component = len(split_id[1])
    date_component = datetime.date(*map(int, split_id[2:]))
    assert split_id[0] == "coda"
    assert uuid_component == 6
    assert date_component == request.created_at.date()


@pytest.mark.django_db
def test__fundingrequest_wizard__first_step__when_valid_data__stores_data_in_session(
    client: Client,
) -> None:
    institution = Institution.objects.create(name="The Institution")

    form_data = {
        "submitter-name": "John Doe",
        "submitter-email": "john.doe@example.com",
        "submitter-orcid": "0000-0000-0000-0000",
        "affiliation-name": str(institution.pk),
    }

    _ = client.post("/fundingrequests/create/", form_data)

    assert client.session["submitter"] == {
        "name": "John Doe",
        "email": "john.doe@example.com",
        "orcid": "0000-0000-0000-0000",
        "affiliation": institution.pk,
    }
