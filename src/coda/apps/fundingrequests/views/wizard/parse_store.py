from coda.apps.publications.dto import JournalDto, PublicationDto
from coda.apps.wizard import Store


def publication_dto_from(store: Store) -> PublicationDto:
    # publication_meta = PublicationMetaDto(**store["publication"])
    # link_form_data = [LinkDto(**link) for link in store["links"]]
    # journal = JournalDto(id=store["journal"])
    # corresponding_author = AuthorDto(**store["corresponding_author"])
    # publication_dto = PublicationDto(
    #     meta=publication_meta,
    #     links=link_form_data,
    #     corresponding_author=corresponding_author,
    #     authors=store["authors"],
    #     journal=journal,
    #     contracts=store["contracts"],
    # )

    publication_dto = PublicationDto(
        **store["publication_step"],
        journal=JournalDto(id=store["journal"]),
        contracts=store["contracts"],
    )

    return publication_dto
