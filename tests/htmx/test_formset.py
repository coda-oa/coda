import pytest
from django.test.client import Client
from django.utils.datastructures import MultiValueDict
from pytest_django.fixtures import SettingsWrapper

from tests.htmx.views import _TestForm, _TestFormset


@pytest.fixture(autouse=True)
def add_form_url_to_django_settings(settings: SettingsWrapper) -> None:
    settings.ROOT_URLCONF = "tests.htmx.urls"


@pytest.mark.django_db
def test__renders_formset_view(client: Client) -> None:
    response = client.get("/")

    assert response.status_code == 200


@pytest.mark.django_db
def test__by_default_view_has_one_form_in_formset(client: Client) -> None:
    response = client.get("/")

    formset: _TestFormset = response.context["formset"]
    assert len(formset.forms) == 1


@pytest.mark.django_db
def test__three_forms__formset_data_includes_all_data() -> None:
    form_data = MultiValueDict(
        {
            "total_forms": ["3"],
            "form-1-field": ["field-1"],
            "form-2-field": ["field-2"],
            "form-3-field": ["field-3"],
        }
    )

    formset = _TestFormset(form_data)
    assert formset.data == [
        {"field": "field-1"},
        {"field": "field-2"},
        {"field": "field-3"},
    ]


@pytest.mark.django_db
def test__formset_with_prefix__formset_parses_data() -> None:
    form_data = MultiValueDict(
        {
            "total_forms": ["3"],
            "prefix-form-1-field": ["field-1"],
            "prefix-form-2-field": ["field-2"],
            "prefix-form-3-field": ["field-3"],
        }
    )

    formset = _TestFormset(form_data, prefix="prefix")
    assert formset.data == [
        {"field": "field-1"},
        {"field": "field-2"},
        {"field": "field-3"},
    ]


@pytest.mark.django_db
def test__two_formsets_with_different_prefixes__formsets_parse_data() -> None:
    form_data = MultiValueDict(
        {
            "total_forms": ["3"],
            "prefix-form-1-field": ["field-1"],
            "prefix-form-2-field": ["field-2"],
            "prefix-form-3-field": ["field-3"],
            "another-prefix": ["another-prefix"],
            "another-prefix-form-1-field": ["another-field-1"],
            "another-prefix-form-2-field": ["another-field-2"],
            "another-prefix-form-3-field": ["another-field-3"],
        }
    )

    formset = _TestFormset(form_data, prefix="prefix")
    another_formset = _TestFormset(form_data, prefix="another-prefix")
    assert formset.data == [
        {"field": "field-1"},
        {"field": "field-2"},
        {"field": "field-3"},
    ]
    assert another_formset.data == [
        {"field": "another-field-1"},
        {"field": "another-field-2"},
        {"field": "another-field-3"},
    ]


@pytest.mark.django_db
def test__valid_forms__formset_is_valid() -> None:
    form_data = MultiValueDict(
        {
            "total_forms": ["3"],
            "form-1-field": ["field-1"],
            "form-2-field": ["field-2"],
            "form-3-field": ["field-3"],
        }
    )

    formset = _TestFormset(form_data)
    assert formset.is_valid()


@pytest.mark.django_db
def test__invalid_form_among_forms__formset_is_invalid() -> None:
    form_data = MultiValueDict(
        {
            "total_forms": ["3"],
            "form-1-field": ["field-1"],
            "form-2-field": ["field-2"],
            "form-3-field": [""],
        }
    )

    formset = _TestFormset(form_data)
    assert not formset.is_valid()


@pytest.mark.django_db
def test__add_form__increases_formset_forms(client: Client) -> None:
    response = client.post("/htmx/", {"total_forms": "1", "form_action_add": "add_form"})

    total_forms = response.context["total_forms"]
    forms = response.context["formset"]
    assert total_forms == 2
    assert len(forms) == 2


@pytest.mark.django_db
def test__add_form_with_initial_data__new_form_is_added_with_data(client: Client) -> None:
    form_data = {
        "total_forms": "1",
        "form-1-field": "field-1",
        "form_action_add": "add_form",
        "initial-field": "initial-field",
    }

    response = client.post("/htmx/", form_data)

    forms = response.context["formset"]
    form = forms[1]
    form.is_valid()
    print(form.initial)
    print(form.cleaned_data)
    assert form.cleaned_data["field"] == "initial-field"


@pytest.mark.django_db
def test__two_forms__remove_second_form__only_renders_first_form(client: Client) -> None:
    form_data = {
        "total_forms": "2",
        "form-1-field": "field-1",
        "form-2-field": "field-2",
        "form_action_delete": "2",
    }

    response = client.post("/htmx/", form_data)

    forms = response.context["formset"]
    first_form: _TestForm = forms[0]
    assert len(forms) == 1
    assert first_form.cleaned_data["field"] == "field-1"


@pytest.mark.django_db
def test__two_forms__remove_first_form__only_renders_second_form(client: Client) -> None:
    form_data = {
        "total_forms": "2",
        "form-1-field": "field-1",
        "form-2-field": "field-2",
        "form_action_delete": "1",
    }

    response = client.post("/htmx/", form_data)

    forms = response.context["formset"]
    first_form: _TestForm = forms[0]
    assert len(forms) == 1
    assert first_form.cleaned_data["field"] == "field-2"


@pytest.mark.django_db
def test__three_forms__removing_second_form__renders_remaining_two_forms(client: Client) -> None:
    form_data = {
        "total_forms": "3",
        "form-1-field": "field-1",
        "form-2-field": "field-2",
        "form-3-field": "field-3",
        "form_action_delete": "2",
    }

    response = client.post("/htmx/", form_data)

    forms = response.context["formset"]
    assert len(forms) == 2
    assert forms[0].cleaned_data["field"] == "field-1"
    assert forms[1].cleaned_data["field"] == "field-3"
