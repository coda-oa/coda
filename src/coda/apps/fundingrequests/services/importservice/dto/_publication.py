import datetime
from typing import Annotated, Literal, Self

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


def _maybe_issn(v: str) -> str:
    if v == "":
        return v

    return issn.Issn(v)


MaybeIssn = Annotated[str, pydantic.PlainValidator(_maybe_issn)]


class PublishingStateImportDto(pydantic.BaseModel):
    state: PublishingStateOptions = "unknown"
    online_date: datetime.date | None = None
    print_date: datetime.date | None = None


class PublicationImportDto(pydantic.BaseModel):
    title: str
    kind: Literal["article", "monograph"]
    eissn: MaybeIssn = pydantic.Field(default="")
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

    @pydantic.model_validator(mode="after")
    def verify_eissn(self) -> Self:
        if self.kind == "article" and self.eissn == "":
            raise pydantic.ValidationError("EISSN must be provided for articles")

        return self
