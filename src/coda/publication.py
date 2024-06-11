import datetime
import enum
from dataclasses import dataclass, field
from typing import NamedTuple, NewType, Self, TypeAlias

from coda.author import AuthorList
from coda.doi import Doi
from coda.string import NonEmptyStr

JournalId = NewType("JournalId", int)
PublicationId = NewType("PublicationId", int)


class UnpublishedState(enum.Enum):
    Unknown = "Unknown"
    Submitted = "Submitted"
    Accepted = "Accepted"
    Rejected = "Rejected"


class License(enum.Enum):
    CC_BY = "CC-BY"
    CC_BY_SA = "CC-BY-SA"
    CC_BY_NC = "CC-BY-NC"
    CC_BY_NC_SA = "CC-BY-NC-SA"
    CC_BY_NC_ND = "CC-BY-NC-ND"
    CC_BY_ND = "CC-BY-ND"
    CC0 = "CC0"
    Unknown = "Unknown"
    Proprietary = "Proprietary"
    None_ = "None"


class OpenAccessType(enum.Enum):
    Gold = "Gold"
    Diamond = "Diamond"
    Hybrid = "Hybrid"
    Unknown = "Unknown"
    Closed = "Closed"


class Unpublished(NamedTuple):
    state: UnpublishedState = UnpublishedState.Unknown

    def name(self) -> str:
        return self.state.name


@dataclass(slots=True, frozen=True)
class Published:
    date: datetime.date

    def __post_init__(self) -> None:
        if self.date is None:
            raise ValueError("Published state requires a date")

    @staticmethod
    def name() -> str:
        return "Published"


PublicationState: TypeAlias = Unpublished | Published


class MediaPublicationStates(NamedTuple):
    online: PublicationState = Unpublished()
    print: PublicationState = Unpublished()


class UserLink(NamedTuple):
    type: str
    value: str

    def __str__(self) -> str:
        return self.value


Link: TypeAlias = UserLink | Doi


PublicationType = NewType("PublicationType", str)
UnknownPublicationType = PublicationType("unknown")


@dataclass(frozen=True)
class Publication:
    id: PublicationId | None
    title: NonEmptyStr
    journal: JournalId
    authors: AuthorList = field(default_factory=AuthorList)
    license: License = License.Unknown
    publication_type: PublicationType = UnknownPublicationType
    open_access_type: OpenAccessType = OpenAccessType.Unknown
    publication_state: MediaPublicationStates = MediaPublicationStates()
    links: set[Link] = field(default_factory=set)

    @classmethod
    def new(
        cls,
        title: NonEmptyStr,
        journal: JournalId,
        authors: AuthorList = AuthorList(),
        license: License = License.Unknown,
        open_access_type: OpenAccessType = OpenAccessType.Unknown,
        publication_state: MediaPublicationStates = MediaPublicationStates(),
        links: set[Link] = set(),
    ) -> Self:
        return cls(
            id=None,
            title=title,
            journal=journal,
            authors=authors,
            license=license,
            open_access_type=open_access_type,
            publication_state=publication_state,
            links=links,
        )
