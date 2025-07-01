from coda.apps.fundingrequests.views.wizard.steps.publisher_step import PublisherStepDto
from coda.apps.publications.dto import JournalDto, MonographDto, PublicationDto
from coda.apps.wizard import Store


def publication_dto_from(store: Store) -> PublicationDto:
    publication_dto = PublicationDto(
        **store["publication_step"],
        journal=JournalDto(id=store["journal"]),
        contracts=store["contracts"],
    )

    return publication_dto


def monograph_dto_from(store: Store) -> MonographDto:
    publisher_step = PublisherStepDto(**store["publisher_step"])
    monograph_dto = MonographDto(
        **store["publication_step"],
        publisher=publisher_step.publisher,
        contracts=publisher_step.contracts,
    )

    return monograph_dto
