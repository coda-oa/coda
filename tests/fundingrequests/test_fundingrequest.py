import datetime

import pytest

from tests.fundingrequests import factory


@pytest.mark.django_db
def test__fundingrequest__has_valid_id_pattern() -> None:
    request = factory.fundingrequest()

    split_id = request.request_id.split("-")
    uuid_component = len(split_id[1])
    date_component = datetime.date(*map(int, split_id[2:]))
    assert split_id[0] == "coda"
    assert uuid_component == 8
    assert date_component == request.created_at.date()


@pytest.mark.django_db
def test__fundingrequest__approve__changes_processing_status() -> None:
    request = factory.fundingrequest()

    request.approve()

    assert request.processing_status == "approved"


@pytest.mark.django_db
def test__fundingrequest__reject__changes_processing_status() -> None:
    request = factory.fundingrequest()

    request.reject()

    assert request.processing_status == "rejected"


@pytest.mark.django_db
def test__fundingrequest__open__changes_processing_status() -> None:
    request = factory.fundingrequest()

    request.open()

    assert request.processing_status == "in_progress"
