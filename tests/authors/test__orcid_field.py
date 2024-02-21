import pytest
from django.core.exceptions import ValidationError

from coda.apps.authors.forms import OrcidField
from tests import test_orcid


def test__orcid_field__is_validated() -> None:
    sut = OrcidField()

    assert sut.clean(test_orcid.JOSIAH_CARBERRY) == test_orcid.JOSIAH_CARBERRY


def test__orcid_field__is_validated__when_empty() -> None:
    sut = OrcidField(required=False)

    assert sut.clean("") == ""


def test__orcid_field__is_validated__when_invalid() -> None:
    sut = OrcidField()

    with pytest.raises(ValidationError):
        sut.clean("invalid")


def test__non_required_orcid_field__is_validated__when_empty() -> None:
    sut = OrcidField(required=False)

    with pytest.raises(ValidationError):
        assert sut.clean("invalid")
