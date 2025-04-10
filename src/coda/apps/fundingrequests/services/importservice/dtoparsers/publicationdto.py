from coda.apps.journals import services as journal_services
from coda.apps.publications.dto import (
    JournalDto,
    LinkDto,
    MonographDto,
    PublicationBaseDto,
    PublicationDto,
    PublicationMetaDto,
)
from coda.apps.publishers.models import Publisher
from coda.domain import issn
from coda.domain.contract import PublisherId
from coda.domain.publication import JournalId
from coda.domain.string import NonEmptyStr

from ..dto import PublicationImportDto
from ..dtoparsers import authordto, conceptdto, contractdto


def parse_dto(import_dto: PublicationImportDto) -> PublicationBaseDto:
    links = [
        LinkDto(
            link_type=link.type,
            link_value=link.value,
        )
        for link in import_dto.links
    ]
    meta = PublicationMetaDto(
        title=import_dto.title,
        publication_type=conceptdto.parse_dto(import_dto.publication_type),
        subject_area=conceptdto.parse_dto(import_dto.subject_area),
        publication_state=import_dto.publishing_state.state,
        online_publication_date=import_dto.publishing_state.online_date,
        print_publication_date=import_dto.publishing_state.print_date,
        license=import_dto.license.name,
        open_access_type=import_dto.open_access_type.value,
    )

    authors = [authordto.parse_dto(author_dto) for author_dto in import_dto.authors]
    contracts = [contractdto.parse_dto(contract_dto) for contract_dto in import_dto.contracts]

    if import_dto.kind == "article":
        return PublicationDto(
            meta=meta,
            journal=_parse_journal(import_dto),
            links=links,
            relevant_authors=authors,
            other_authors=[],
            contracts=contracts,
        )
    elif import_dto.kind == "monograph":
        return MonographDto(
            meta=meta,
            publisher=_parse_publisher(import_dto),
            links=links,
            relevant_authors=authors,
            other_authors=[],
            contracts=contracts,
        )


def _parse_journal(import_dto: PublicationImportDto) -> JournalDto:
    journal = journal_services.find_by_eissn(issn.Issn(import_dto.eissn))
    if journal:
        return JournalDto(id=JournalId(journal.id))

    return JournalDto(
        id=journal_services.create(
            title=NonEmptyStr(import_dto.journal_name),
            eissn=issn.Issn(import_dto.eissn),
            publisher_id=_parse_publisher(import_dto),
        )
    )


def _parse_publisher(import_dto: PublicationImportDto) -> PublisherId:
    publisher, _ = Publisher.objects.get_or_create(name=import_dto.publisher_name)
    return PublisherId(publisher.id)
