from coda.apps.publications.dto import JournalDto, LinkDto, PublicationDto, PublicationMetaDto
from coda.apps.wizard import Store


def publication_dto_from(store: Store) -> PublicationDto:
    publication_meta: PublicationMetaDto = store["publication"]
    link_form_data: list[LinkDto] = store["links"]
    journal = JournalDto(journal_id=store["journal"])
    publication_dto = PublicationDto(
        meta=publication_meta,
        links=link_form_data,
        authors=store["authors"],
        journal=journal,
        contracts=store["contracts"],
    )

    return publication_dto
