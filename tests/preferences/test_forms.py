import pytest
from django.forms import ModelChoiceField
from django.utils import timezone

from coda.apps.institutions.models import Institution
from coda.apps.preferences.forms import GlobalPreferencesForm


@pytest.mark.django_db
def test__global_preferences_home_institution_dropdown__excludes_archived_institutions() -> None:
    active_institution = Institution.objects.create(name="Active University")
    archived_institution = Institution.objects.create(
        name="Archived University", archived_at=timezone.now()
    )

    form = GlobalPreferencesForm()
    home_institution_field = form.fields["home_institution"]
    assert isinstance(home_institution_field, ModelChoiceField)
    home_institution_queryset = home_institution_field.queryset
    assert home_institution_queryset is not None

    assert active_institution in home_institution_queryset
    assert archived_institution not in home_institution_queryset
