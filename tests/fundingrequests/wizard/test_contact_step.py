from dataclasses import asdict

from django.test import RequestFactory

from coda.apps.fundingrequests.views.wizard.steps.contact_step import ExtraContactStep
from coda.fundingrequest import FilledContact
from coda.string import NonEmptyStr
from tests.test_wizard import DictStore


def test__contact_step__form_valid__is_valid() -> None:
    contact = FilledContact(name=NonEmptyStr("John Doe"), email="j.doe@example.com")
    sut = ExtraContactStep()

    request = RequestFactory().post("/", data=asdict(contact))

    assert sut.is_valid(request, DictStore())


def test__contact_step__empty_form__is_valid() -> None:
    contact = {"name": "", "email": ""}
    sut = ExtraContactStep()

    request = RequestFactory().post("/", data=contact)

    assert sut.is_valid(request, DictStore())


def test__contact_step__name_but_no_email__is_not_valid() -> None:
    contact = {"name": "John Doe", "email": ""}
    sut = ExtraContactStep()

    request = RequestFactory().post("/", data=contact)

    assert not sut.is_valid(request, DictStore())


def test__contact_step__email_but_no_name__is_not_valid() -> None:
    contact = {"name": "", "email": "j.doe@example.com"}
    sut = ExtraContactStep()

    request = RequestFactory().post("/", data=contact)

    assert not sut.is_valid(request, DictStore())


def test__contact_step__done__stores__contact_in_store() -> None:
    contact = FilledContact(name=NonEmptyStr("John Doe"), email="j.doe@example.com")
    sut = ExtraContactStep()

    request = RequestFactory().post("/", data=asdict(contact))

    store = DictStore()
    sut.done(request, store)

    assert FilledContact(**store["contact"]) == contact


def test__contact_step__empty_form__done__does_not_store_contact_in_store() -> None:
    contact = {"name": "", "email": ""}
    sut = ExtraContactStep()

    request = RequestFactory().post("/", data=contact)

    store = DictStore()
    sut.done(request, store)

    assert "contact" not in store


def test__contact_step__contact_in_store__done_with_empty_form__removes_contact_from_store() -> (
    None
):
    contact = FilledContact(name=NonEmptyStr("John Doe"), email="j.doe@example.com")
    sut = ExtraContactStep()
    store = DictStore()
    store["contact"] = asdict(contact)
    store.save()

    request = RequestFactory().post("/", data={"name": "", "email": ""})

    sut.done(request, store)

    assert "contact" not in store
