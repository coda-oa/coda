from typing import Any

from coda.apps.htmx_components.converters import to_htmx_formset_data
from coda.apps.publications.dto import (
    LinkDto,
    PublicationBaseDto,
    PublicationDto,
    PublicationMetaDto,
)
from tests import domainfactory


def stepdata(publication: PublicationBaseDto | None = None) -> dict[str, Any]:
    publication_ = publication or PublicationDto.from_publication(domainfactory.publication())
    meta = publication_.meta
    relevant_authors = to_htmx_formset_data(
        [author.to_post_data() for author in publication_.relevant_authors],
        prefix="relevant-authors",
    )
    authors = _serialize_authors(publication_.other_authors)
    concepts = _concepts_to_json(meta)
    meta_reduced = _reduce_meta(meta)
    link_form_data = _serialize_links(publication_.links)

    formdata = meta_reduced | relevant_authors | {"authors": authors} | concepts | link_form_data
    return formdata


def _serialize_authors(authors: list[str]) -> str:
    return ",".join(authors)


def _reduce_meta(meta: PublicationMetaDto) -> dict[str, Any]:
    return meta.to_post_data(exclude={"subject_area", "publication_type"})


def _serialize_links(links: list[LinkDto]) -> dict[str, list[str]]:
    link_form_data: dict[str, list[str]] = {"link_type": [], "link_value": []}
    for link in links:
        link_form_data["link_type"].append(link.link_type)
        link_form_data["link_value"].append(link.link_value)
    return link_form_data


def _concepts_to_json(meta: PublicationMetaDto) -> dict[str, Any]:
    return {
        "subject_area": meta.subject_area.model_dump_json(),
        "publication_type": meta.publication_type.model_dump_json(),
    }
