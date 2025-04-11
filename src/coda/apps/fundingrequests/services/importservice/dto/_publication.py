import datetime
from typing import Annotated, Literal

import pydantic

from coda.domain import issn
from coda.domain.publication import License, OpenAccessType, links

from ._author import AuthorImportDto
from ._contract import ContractImportDto
from ._vocabulary import ConceptImportDto


def _valid_link_type(v: str) -> str:
    if not links.valid_link_type(v):
        raise ValueError(f"Link type '{v}' is not valid")
    return v


LinkType = Annotated[str, pydantic.PlainValidator(_valid_link_type)]


class LinkImportDto(pydantic.BaseModel):
    type: LinkType
    value: str


PublishingStateOptions = Literal["unknown", "submitted", "accepted", "rejected", "published"]
Issn = Annotated[str, pydantic.PlainValidator(issn.Issn)]


class PublishingStateImportDto(pydantic.BaseModel):
    state: PublishingStateOptions = "unknown"
    online_date: datetime.date | None = None
    print_date: datetime.date | None = None


class PublicationImportDto(pydantic.BaseModel):
    title: str
    kind: Literal["article", "monograph"]
    eissn: Issn
    journal_name: str = "Imported nameless journal"
    publisher_name: str = "Imported nameless publisher"
    authors: list[AuthorImportDto] = pydantic.Field(default_factory=list)
    license: License = License.Unknown
    publishing_state: PublishingStateImportDto = pydantic.Field(
        default_factory=PublishingStateImportDto
    )
    open_access_type: OpenAccessType
    links: list[LinkImportDto] = pydantic.Field(default_factory=list)
    contracts: list[ContractImportDto] = pydantic.Field(default_factory=list)
    subject_area: ConceptImportDto = pydantic.Field(default_factory=ConceptImportDto)
    publication_type: ConceptImportDto = pydantic.Field(default_factory=ConceptImportDto)
