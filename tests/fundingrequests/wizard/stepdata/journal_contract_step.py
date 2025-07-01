from typing import Any

from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.publications.dto import PublicationDto
from tests import domainfactory


def stepdata(publication_dto: PublicationDto | None = None) -> dict[str, Any]:
    publication_dto = publication_dto or PublicationDto.from_publication(
        domainfactory.publication()
    )

    journal_id = publication_dto.journal.id
    journal_post_data = {"journal": journal_id}
    contracts = to_htmx_formset_data(
        [{"contract": c.contract, "year": c.year} for c in publication_dto.contracts],
        prefix="contracts",
    )

    return journal_post_data | contracts
