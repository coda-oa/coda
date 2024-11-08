from typing import Any

from coda.apps.publications.dto import LinkDto, PublicationDto, PublicationMetaDto
from tests import domainfactory


def empty_stepdata() -> dict[str, str]:
    return {
        "title": "",
        "authors": "",
        "open_access_type": "",
        "license": "",
        "publication_state": "",
        "online_publication_date": "",
        "print_publication_date": "",
        "subject_area": "",
        "publication_type": "",
        "corresponding_author-name": "",
        "corresponding_author-email": "",
        "corresponding_author-orcid": "",
    }


def stepdata(publication: PublicationDto | None = None) -> dict[str, Any]:
    publication = publication or PublicationDto.from_publication(domainfactory.publication())
    meta = publication.meta
    authors = _serialize_authors(publication.authors)
    concepts = _concepts_to_json(meta)
    meta_reduced = _reduce_meta(meta)
    link_form_data = _serialize_links(publication.links)

    formdata = (
        meta_reduced
        | {"authors": authors}
        | concepts
        | link_form_data
        | publication.corresponding_author.to_post_data(prefix="corresponding_author")
    )
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
