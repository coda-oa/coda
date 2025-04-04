import datetime
import enum
from abc import ABC
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    NamedTuple,
    NewType,
    Self,
    TypeAlias,
    TypeGuard,
    TypeVar,
)

from coda.domain.author import Author, AuthorNames
from coda.domain.contract import PublisherId
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import UnknownConcept, VocabularyConcept

from .links import Link

if TYPE_CHECKING:
    from coda.domain.contract import ContractYear


JournalId = NewType("JournalId", int)


class PublicationId(int):
    __slots__ = ()


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
    Opt_in = "Opt-in"
    Opt_out = "Opt-out"
    Unknown = "Unknown"
    Closed = "Closed"


class Unpublished(NamedTuple):
    state: UnpublishedState = UnpublishedState.Unknown

    @classmethod
    def of(cls, state: str) -> "Unpublished":
        try:
            state_with_first_upper = state[0].upper() + state[1:]
            return cls(UnpublishedState(state_with_first_upper))
        except ValueError:
            raise ValueError(f"Unknown unpublished state: {state}")

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


class Authors(tuple[Author, ...]):
    __slots__ = ()

    def __new__(cls, iterable: Iterable[Author] = ()) -> "Authors":
        instance = super().__new__(cls, iterable)
        submitting_authors = tuple(author for author in instance if author.is_submitter())

        if len(submitting_authors) > 1:
            raise ValueError("Publication can only have one submitting author")

        return instance


PublicationKind = TypeVar("PublicationKind", bound="BasePublication")


@dataclass(kw_only=True)
class BasePublication(ABC):
    id: PublicationId | None
    title: NonEmptyStr
    relevant_authors: Authors = Authors()
    other_authors: AuthorNames = field(default_factory=AuthorNames)
    license: License = field(default=License.Unknown)
    subject_area: VocabularyConcept = field(default=UnknownConcept)
    publication_type: VocabularyConcept = field(default=UnknownConcept)
    open_access_type: OpenAccessType = field(default=OpenAccessType.Unknown)
    publication_state: PublicationState = field(default=Unpublished())
    contracts: tuple["ContractYear", ...] = ()
    links: set[Link] = field(default_factory=set)

    def is_published(self) -> bool:
        return isinstance(self.publication_state, Published)

    def is_kind(self, kind: type[PublicationKind]) -> TypeGuard[PublicationKind]:
        return isinstance(self, kind)


@dataclass(kw_only=True)
class Publication(BasePublication):
    journal: JournalId

    @classmethod
    def new(
        cls,
        title: NonEmptyStr,
        journal: JournalId,
        relevant_authors: Iterable[Author] = (),
        other_authors: AuthorNames = AuthorNames(),
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
            relevant_authors=Authors(relevant_authors),
            other_authors=other_authors,
            license=license,
            subject_area=subject_area,
            publication_type=publication_type,
            open_access_type=open_access_type,
            publication_state=publication_state,
            links=links or set(),
        )


@dataclass(kw_only=True)
class Monograph(BasePublication):
    publisher: PublisherId

    @classmethod
    def new(
        cls,
        title: NonEmptyStr,
        publisher: PublisherId,
        relevant_authors: Iterable[Author] = (),
        other_authors: AuthorNames = AuthorNames(),
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
            publisher=publisher,
            relevant_authors=Authors(relevant_authors),
            other_authors=other_authors,
            license=license,
            subject_area=subject_area,
            publication_type=publication_type,
            open_access_type=open_access_type,
            publication_state=publication_state,
            links=links or set(),
        )
