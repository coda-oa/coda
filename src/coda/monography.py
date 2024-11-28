from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coda.author import Author, AuthorList
from coda.publication import (
    License,
    Link,
    OpenAccessType,
    PublicationId,
    PublicationState,
    Unpublished,
)
from coda.string import NonEmptyStr
from coda.vocabulary import UnknownConcept, VocabularyConcept

if TYPE_CHECKING:
    from coda.contract import ContractId


@dataclass(frozen=True, slots=True)
class PublicationMetaData:
    title: NonEmptyStr
    corresponding_author: Author
    authors: AuthorList = field(default_factory=AuthorList)
    license: License = License.Unknown
    subject_area: VocabularyConcept = UnknownConcept
    publication_type: VocabularyConcept = UnknownConcept
    open_access_type: OpenAccessType = OpenAccessType.Unknown
    publication_state: PublicationState = Unpublished()
    contracts: set["ContractId"] = field(default_factory=set)
    links: set[Link] = field(default_factory=set)


@dataclass
class Monography:
    id: PublicationId | None
    title: NonEmptyStr
    corresponding_author: Author
    authors: AuthorList = field(default_factory=AuthorList)
    license: License = License.Unknown
    subject_area: VocabularyConcept = UnknownConcept
    publication_type: VocabularyConcept = UnknownConcept
    open_access_type: OpenAccessType = OpenAccessType.Unknown
    publication_state: PublicationState = Unpublished()
    contracts: set["ContractId"] = field(default_factory=set)
    links: set[Link] = field(default_factory=set)
