from typing import cast
import pytest

from coda.apps.authors.dto import author_dto_from_model
from coda.apps.authors.models import Author
from coda.apps.publications.services import publication_update
from tests import factory
from tests.assertions import assert_publication_equal


@pytest.mark.django_db
def test__update_fundingrequest_publication__updates_publication() -> None:
    publication = factory.publication()
    new_journal = factory.journal()
    links = factory.link_dtos()
    new_publication_data = factory.publication_dto(new_journal.pk, links=links)

    publication_update(publication, new_publication_data)

    publication.refresh_from_db()
    author = author_dto_from_model(cast(Author, publication.submitting_author))
    assert_publication_equal(new_publication_data, author, publication)
