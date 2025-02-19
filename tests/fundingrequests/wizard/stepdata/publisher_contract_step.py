from typing import Any
from coda.apps.fundingrequests.views.wizard.steps.publisher_step import PublisherStepDto
from coda.apps.publications.dto import MonographDto
from tests import domainfactory


def stepdata(monograph_dto: MonographDto | None = None) -> dict[str, Any]:
    monograph_dto = monograph_dto or MonographDto.from_monograph(domainfactory.monograph())
    return PublisherStepDto(
        publisher=monograph_dto.publisher,
        contracts=monograph_dto.contracts,
    ).page_input()
