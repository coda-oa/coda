from collections.abc import Callable
from typing import cast

from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId, Doi, Link, link_registry

type FundingOrganizationLink = Doi | Ror | CrossrefId

_registry = link_registry(Doi, Ror, CrossrefId)

_LinkTypes: dict[str, type[Link]] = _registry.by_type
_LoweredLinkTypes: dict[str, Callable[[str], Link]] = _registry.by_lower


def link_types() -> list[str]:
    return list(_LinkTypes.keys())


def create_link(link_type: str, link_value: str) -> FundingOrganizationLink:
    return cast(FundingOrganizationLink, _registry.create_link(link_type, link_value))
