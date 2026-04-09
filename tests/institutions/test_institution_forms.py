import pytest
from coda.apps.institutions.forms import InstitutionForm
from coda.apps.institutions.models import Institution


@pytest.mark.django_db
def test__institution_form__created__internal_id_field_included() -> None:
    form = InstitutionForm()
    assert "internal_id" in form.fields


@pytest.mark.django_db
def test__blank_internal_id__form_saved__internal_id_auto_generated() -> None:
    form_data = {
        "name": "Test University",
        "parent": "",
        "internal_id": "",
    }
    form = InstitutionForm(data=form_data)

    assert form.is_valid()
    inst = form.save()

    assert inst.internal_id
    assert inst.internal_id.startswith("inst_")
    assert len(inst.internal_id) == 13


@pytest.mark.django_db
def test__custom_internal_id_provided__form_saved__uses_provided_id() -> None:
    form_data = {
        "name": "Custom University",
        "parent": "",
        "internal_id": "custom_test_123",
    }
    form = InstitutionForm(data=form_data)

    assert form.is_valid()
    inst = form.save()

    assert inst.internal_id == "custom_test_123"


@pytest.mark.django_db
def test__duplicate_internal_id_exists__form_validated__validation_fails() -> None:
    Institution.objects.create(name="Existing", internal_id="duplicate_id")

    form_data = {
        "name": "New University",
        "parent": "",
        "internal_id": "duplicate_id",
    }
    form = InstitutionForm(data=form_data)

    assert not form.is_valid()
    assert "internal_id" in form.errors
