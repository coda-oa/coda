from collections.abc import Generator

import pytest
from django.conf import Settings

from coda.apps.checklist.services import get_checkfactory


def test__get_checkfactory__loads_checkfactory_from_settings() -> None:
    from tests.checks.checkfactory import checkfactory as expected_checkfactory

    factory = get_checkfactory()
    assert factory == expected_checkfactory


@pytest.fixture
def production_checkfactory(settings: Settings) -> Generator[None]:
    settings.CODA_CHECKLIST_FACTORY = "coda.checks.checkfactory"  # type: ignore
    yield


@pytest.mark.usefixtures("production_checkfactory")
def test__get_checkfactory__production_settings__loads_checkfactory_from_settings() -> None:
    from coda.checks.checkfactory import checkfactory as expected_checkfactory

    factory = get_checkfactory()
    assert factory == expected_checkfactory
