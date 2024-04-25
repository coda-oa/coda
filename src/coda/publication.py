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


class License(enum.Enum):
    CC_BY = enum.auto()
    CC_BY_SA = enum.auto()
    CC_BY_NC = enum.auto()
    CC_BY_NC_SA = enum.auto()
    CC_BY_ND = enum.auto()
    CC_BY_NC_ND = enum.auto()
    CC0 = enum.auto()
    Unknown = enum.auto()


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


class Publication(NamedTuple):
    id: PublicationId
    title: NonEmptyStr
    journal: JournalId
    authors: AuthorList = AuthorList()
    license: License = License.Unknown
    publication_state: PublicationState = Unpublished()
    links: set[Link] = set()
