"""Shared fixtures for fundingrequests tests."""

import pytest

from coda.apps.journals import services as journal_services
from coda.apps.journals.models import Journal
from coda.domain.contract import PublisherId
from coda.domain.issn import Issn
from coda.domain.string import NonEmptyStr
from tests import modelfactory


@pytest.fixture
def test_journal() -> Journal:
    """Create and return a test journal."""
    publisher_name = "Test Publisher"
    journal_title = "Nature"
    journal_eissn = "1476-4687"

    publisher_id = PublisherId(modelfactory.publisher(name=publisher_name).pk)
    journal_id = journal_services.create(
        title=NonEmptyStr(journal_title),
        eissn=Issn(journal_eissn),
        publisher_id=publisher_id,
    )

    return Journal.objects.get(pk=int(journal_id))
