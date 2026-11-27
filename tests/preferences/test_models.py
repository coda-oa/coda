import pytest

from coda.apps.preferences.models import GlobalPreferences
from coda.domain.money import Currency


@pytest.mark.django_db
def test__get_home_currency__valid_stored_code__returns_currency() -> None:
    GlobalPreferences.set_home_currency(Currency.USD)

    assert GlobalPreferences.get_home_currency() == Currency.USD


@pytest.mark.django_db
def test__get_home_currency__unparseable_stored_value__falls_back_to_eur() -> None:
    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_currency = "XYZ"
    prefs.save()

    assert GlobalPreferences.get_home_currency() == Currency.EUR
