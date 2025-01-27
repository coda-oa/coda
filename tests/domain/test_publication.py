from datetime import date
from typing import cast

import pytest

from coda.author import Author
from coda.publication import JournalId, Publication, Published
from coda.string import NonEmptyStr


def test__published_state__requires_at_least_one_date() -> None:
    with pytest.raises(ValueError):
        Published(online=cast(date, None), print=cast(date, None))


def test__new_publication__assigns_corresponding_author_role() -> None:
    author = Author.new(NonEmptyStr("John Doe"), "j.doe@doeworld.com")
    publication = Publication.new(
        title=NonEmptyStr("Publication Title"), journal=JournalId(0), corresponding_author=author
    )

    assert publication.corresponding_author.is_corresponding_author()
