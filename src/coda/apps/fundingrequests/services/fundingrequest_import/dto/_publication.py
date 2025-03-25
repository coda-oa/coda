import datetime
from typing import Annotated, Literal

import pydantic

from coda import issn
from coda.apps.contracts import repository as contract_repository
from coda.apps.journals import services as journal_services
from coda.apps.publishers.models import Publisher
from coda.contract import Contract, PublisherId
from coda.publication import (
    Authors,
    BasePublication,
    JournalId,
    License,
    Link,
    Monograph,
    OpenAccessType,
    Publication,
    PublicationState,
    Published,
    Unpublished,
    links,
)
from coda.string import NonEmptyStr

from ._author import AuthorImportDto
from ._contract import ContractImportDto
from ._vocabulary import ConceptImportDto


def _valid_link_type(v: str) -> str:
    if v not in links.link_types():
        raise ValueError(f"Link type '{v}' is not valid")
    return v


LinkType = Annotated[str, pydantic.PlainValidator(_valid_link_type)]


class LinkImportDto(pydantic.BaseModel):
    type: LinkType
    value: str

    def parse(self) -> links.Link:
        return links.create_link(self.type, self.value)


PublishingStateOptions = Literal["unknown", "submitted", "accepted", "rejected", "published"]
Issn = Annotated[str, pydantic.PlainValidator(issn.Issn)]


class PublishingStateImportDto(pydantic.BaseModel):
    state: PublishingStateOptions = "unknown"
    online_date: datetime.date | None = None
    print_date: datetime.date | None = None

    def parse(self) -> PublicationState:
        if self.state == "published":
            return Published(online=self.online_date, print=self.print_date)

        return Unpublished.of(self.state)


class PublicationImportDto(pydantic.BaseModel):
    title: str
    kind: Literal["article", "monograph"]
    eissn: str
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

    def parse(self) -> BasePublication:
        subject_area = self.subject_area.parse()
        publication_type = self.publication_type.parse()
        publishing_state = self.publishing_state.parse()
        authors = self._parse_authors()
        links = self._parse_links()

        publication: BasePublication
        if self.kind == "article":
            publication = Publication.new(
                title=NonEmptyStr(self.title),
                journal=self._parse_journal_id(),
                license=self.license,
                open_access_type=self.open_access_type,
                publication_state=publishing_state,
                relevant_authors=authors,
                links=links,
                subject_area=subject_area,
                publication_type=publication_type,
            )

        elif self.kind == "monograph":
            publication = Monograph.new(
                title=NonEmptyStr(self.title),
                publisher=self._parse_publisher_id(),
                license=self.license,
                open_access_type=self.open_access_type,
                publication_state=publishing_state,
                relevant_authors=authors,
                links=links,
                subject_area=subject_area,
                publication_type=publication_type,
            )

        publication.contracts = tuple(
            self._get_contract(contract_dto).in_year(contract_dto.year)
            for contract_dto in self.contracts
        )

        return publication

    def _parse_links(self) -> set[Link]:
        return {link.parse() for link in self.links}

    def _parse_authors(self) -> Authors:
        return Authors([author.parse() for author in self.authors])

    def _get_contract(self, contract_dto: ContractImportDto) -> Contract:
        contract = contract_repository.get_by_name(contract_dto.name)
        if not contract:
            contract = Contract.new(name=NonEmptyStr(contract_dto.name))
            contract.id = contract_repository.save(contract)

        return contract

    def _parse_journal_id(self) -> JournalId:
        journal = journal_services.find_by_eissn(issn.Issn(self.eissn))
        if journal:
            journal_id = JournalId(journal.id)
        else:
            publisher, _ = Publisher.objects.get_or_create(name=self.publisher_name)
            journal_id = journal_services.create(
                NonEmptyStr(self.journal_name),
                issn.Issn(self.eissn),
                PublisherId(publisher.id),
            )

        return journal_id

    def _parse_publisher_id(self) -> PublisherId:
        publisher, _ = Publisher.objects.get_or_create(name=self.publisher_name)
        return PublisherId(publisher.id)
