"""RORClient for batch funder resolution via the ROR API.

Uses the ROR API v2 /organizations endpoint with OR query syntax
to resolve multiple funder identifiers in a single API call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import httpx

from .exceptions import RORClientError
from coda.domain.institution.links import Ror
from coda.domain.publication.links import CrossrefId, Link


class HttpGetClient(Protocol):
    def get(self, url: str, *, params: Any, timeout: int, follow_redirects: bool) -> Any: ...


@dataclass(frozen=True)
class RORRecord:
    """A single record returned by the ROR API."""

    id: str
    name: str
    external_ids: dict[str, list[str]] = field(default_factory=dict)

    def to_links(self) -> list[Link]:
        """Convert this ROR record into domain Link objects.

        Returns a ``Ror`` link from the record's own ID, plus a ``CrossrefId``
        from the first ``fundref`` external ID when present and non-empty.
        """
        links: list[Link] = [Ror(self.id)]
        for lt, values in self.external_ids.items():
            if lt == "fundref" and values:
                links.append(CrossrefId(values[0]))
        return links

    @staticmethod
    def from_api(item: dict[str, Any]) -> RORRecord:
        ext_ids: dict[str, list[str]] = {}
        for entry in item.get("external_ids", []):
            ext_ids[entry["type"]] = entry.get("all", [])
        # Extract display name from names array (prefer ror_display type)
        names: list[dict[str, Any]] = item.get("names", [])
        name = _extract_display_name(names)
        return RORRecord(
            id=item["id"],
            name=name,
            external_ids=ext_ids,
        )


def _extract_display_name(names: list[dict[str, Any]]) -> str:
    """Extract the primary display name from a ROR API names array.

    Prefers the entry with 'ror_display' in its types, falls back to
    the first entry with 'label', then to the first entry overall.
    """
    if not names:
        return "Unknown"
    for entry in names:
        if "ror_display" in entry.get("types", []):
            return cast(str, entry["value"])
    for entry in names:
        if "label" in entry.get("types", []):
            return cast(str, entry["value"])
    return cast(str, names[0]["value"])


class RORClient:
    BASE_URL = "https://api.ror.org/v2/organizations"

    def __init__(self, http_client: HttpGetClient | None = None) -> None:
        self._http = http_client or httpx

    def resolve_by_ids(self, links: Sequence[Link]) -> dict[str, RORRecord]:
        if not links:
            return {}

        query = " OR ".join(f'"{str(link)}"' for link in links)

        all_items: list[dict[str, Any]] = []
        page = 1

        while True:
            params: dict[str, Any] = {"query": query, "all_status": ""}
            if page > 1:
                params["page"] = page

            try:
                response = self._http.get(
                    self.BASE_URL,
                    params=params,
                    timeout=30,
                    follow_redirects=True,
                ).raise_for_status()
                data: dict[str, Any] = response.json()
            except Exception as e:
                raise RORClientError(f"ROR API request failed: {e}") from e

            items = data.get("items", [])
            all_items.extend(items)

            total = data.get("number_of_results", 0)
            if len(all_items) >= total:
                break

            page += 1

        records = [RORRecord.from_api(item) for item in all_items]

        input_strings = {str(link) for link in links}
        result: dict[str, RORRecord] = {}

        for record in records:
            all_ids: set[str] = set()
            for id_list in record.external_ids.values():
                all_ids.update(id_list)
            all_ids.add(record.id)
            ror_suffix = record.id.rsplit("/", 1)[-1]
            all_ids.add(ror_suffix)

            matched_inputs = input_strings & all_ids
            for match in matched_inputs:
                result[match] = record

        return result
