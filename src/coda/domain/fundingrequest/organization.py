from collections.abc import Iterable
from dataclasses import dataclass

from coda.domain.publication.links import Link

from .fundingrequest import FundingOrganizationId


def _merge_links(base: Iterable[Link], override: Iterable[Link]) -> list[Link]:
    """Merge two lists of links, with ``override`` types taking priority."""
    override_by_type = {link.type(): link for link in override}
    merged = {link.type(): link for link in base if link.type() not in override_by_type}
    merged.update(override_by_type)
    return list(merged.values())


@dataclass(frozen=True)
class FunderRecord:
    name: str
    links: tuple[Link, ...] = ()
    organization_id: FundingOrganizationId | None = None

    def with_id(self, organization_id: FundingOrganizationId) -> "FunderRecord":
        return FunderRecord(
            name=self.name,
            links=self.links,
            organization_id=organization_id,
        )

    def revised(
        self,
        name: str | None = None,
        links: Iterable[Link] | None = None,
    ) -> "FunderRecord":
        if name is None and links is None:
            return self
        new_name = name if name is not None else self.name
        new_links = _merge_links(self.links, list(links)) if links is not None else self.links
        return FunderRecord(
            name=new_name, links=tuple(new_links), organization_id=self.organization_id
        )


def preview_merge_funders(
    target_name: str,
    source_links: list[Link],
    target_links: list[Link],
) -> FunderRecord:
    """Compute the merged result of combining two funding organizations.

    Returns a FunderRecord with the target's name and merged links,
    where target links take priority over source links.
    """
    merged = FunderRecord(
        name=target_name,
        links=tuple(source_links),
    )
    return merged.revised(links=target_links)
