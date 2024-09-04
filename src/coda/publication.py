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
    online: datetime.date | None = None
    print: datetime.date | None = None

    def __post_init__(self) -> None:
        if (self.online, self.print) == (None, None):
            raise ValueError("Published state requires at least one date")

    @staticmethod
    def name() -> str:
        return "Published"


PublicationState: TypeAlias = Unpublished | Published


class UserLink(NamedTuple):
    type: str
    value: str
    url_prefix: str = ""

    @property
    def url(self) -> str:
        return self.url_prefix + self.value

    def __str__(self) -> str:
        return self.value


Link: TypeAlias = UserLink | Doi


ConceptId = NewType("ConceptId", str)
VocabularyId = NewType("VocabularyId", int)


class VocabularyConcept(NamedTuple):
    id: ConceptId
    vocabulary: VocabularyId


UnknownConcept = VocabularyConcept(ConceptId("unknown"), VocabularyId(0))


@dataclass(frozen=True)
class Publication:
    id: PublicationId | None
    title: NonEmptyStr
    journal: JournalId
    authors: AuthorList = field(default_factory=AuthorList)
    license: License = License.Unknown
    subject_area: VocabularyConcept = UnknownConcept
    publication_type: VocabularyConcept = UnknownConcept
    open_access_type: OpenAccessType = OpenAccessType.Unknown
    publication_state: PublicationState = Unpublished()
    links: set[Link] = field(default_factory=set)

    @classmethod
    def new(
        cls,
        title: NonEmptyStr,
        journal: JournalId,
        authors: AuthorList = AuthorList(),
        license: License = License.Unknown,
        subject_area: VocabularyConcept = UnknownConcept,
        publication_type: VocabularyConcept = UnknownConcept,
        open_access_type: OpenAccessType = OpenAccessType.Unknown,
        publication_state: PublicationState = Unpublished(),
        links: set[Link] | None = None,
    ) -> Self:
        return cls(
            id=None,
            title=title,
            journal=journal,
            authors=authors,
            license=license,
            subject_area=subject_area,
            publication_type=publication_type,
            open_access_type=open_access_type,
            publication_state=publication_state,
            links=links or set(),
        )
