from datetime import date
from typing import cast

import pytest

from coda.author import Role
from coda.publication import JournalId, Publication, Published
from coda.string import NonEmptyStr
from tests import domainfactory


def test__published_state__requires_at_least_one_date() -> None:
    with pytest.raises(ValueError):
        Published(online=cast(date, None), print=cast(date, None))


def test__publication__can_only_have_one_submitting_author() -> None:
    first = domainfactory.author(role=Role.SUBMITTER)
    second = domainfactory.author(role=Role.SUBMITTER)
    third = domainfactory.author(role=Role.SUBMITTING_CORRESPONDING_AUTHOR)

    with pytest.raises(ValueError):
        Publication.new(
            journal=JournalId(1),
            title=NonEmptyStr("A Title"),
            relevant_authors=[first, second],
        )

    with pytest.raises(ValueError):
        Publication.new(
            journal=JournalId(1),
            title=NonEmptyStr("A Title"),
            relevant_authors=[first, third],
        )
