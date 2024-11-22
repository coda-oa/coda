import pytest

from coda.apps.publications.repositories import publication_repository
from coda.publication import JournalId
from tests import domainfactory, modelfactory
from tests.publications.test_publication_services import assert_publication_eq


@pytest.mark.django_db
def test__saved_publication__first__returns_publication() -> None:
    journal = JournalId(modelfactory.journal().id)
    publication = domainfactory.publication(journal=journal)
    publication_repository.save(publication)

    actual = publication_repository.first()

    assert actual is not None
    assert_publication_eq(actual, publication)
