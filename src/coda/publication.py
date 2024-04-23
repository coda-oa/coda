import datetime
import enum
from typing import NamedTuple, NewType, TypeAlias

from coda.author import AuthorList
from coda.doi import Doi
from coda.string import NonEmptyStr

JournalId = NewType("JournalId", int)
PublicationId = NewType("PublicationId", int)


class State(enum.Enum):
    UNKNOWN = enum.auto()
    SUBMITTED = enum.auto()
    ACCEPTED = enum.auto()
    REJECTED = enum.auto()


class Unpublished(NamedTuple):
    state: State = State.UNKNOWN


class Published(NamedTuple):
    date: datetime.date


PublicationState: TypeAlias = Unpublished | Published


class UserLink(NamedTuple):
    type: str
    value: str

    def __str__(self) -> str:
        return self.value


Link: TypeAlias = str | UserLink | Doi


class Publication:
    def __init__(
        self,
        id: PublicationId,
        title: str,
        journal: JournalId,
        authors: AuthorList | None = None,
    ) -> None:
        self.id = id
        self.title = NonEmptyStr(title)
        self.journal = journal
        self.authors = authors or AuthorList()
        self.publication_state: PublicationState = Unpublished()
        self._links: set[Link] = set()

    def add_link(self, link: Link) -> None:
        self._links.add(link)

    @property
    def links(self) -> list[Link]:
        return list(self._links)
