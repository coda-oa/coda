from typing import cast
import pytest

from coda.apps.authors.dto import author_dto_from_model
from coda.apps.authors.models import Author
from coda.apps.publications.services import publication_create, publication_update
from tests import factory
from tests.assertions import assert_publication_equal


@pytest.mark.django_db
def test__create_publication__creates_a_publication_based_on_given_data() -> None:
    author = factory.author()
    journal = factory.journal()
    links = factory.link_dtos()
    publication_dto = factory.publication_dto(journal.pk, links=links)

    publication = publication_create(publication_dto, author, journal)

    author_dto = author_dto_from_model(author)
    assert_publication_equal(publication_dto, author_dto, publication)


@pytest.mark.django_db
def test__update_publication__updates_publication_based_on_given_data() -> None:
    publication = factory.publication()
    new_journal = factory.journal()
    links = factory.link_dtos()
    new_publication_data = factory.publication_dto(new_journal.pk, links=links)

    publication_update(publication, new_publication_data)

    publication.refresh_from_db()
    author = author_dto_from_model(cast(Author, publication.submitting_author))
    assert_publication_equal(new_publication_data, author, publication)
