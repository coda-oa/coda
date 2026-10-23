"""Chart row -> statistics filter link (§2 #7).

Clicking a chart row filters the statistics page itself: the row's value joins
the page's facet params and the region re-renders with exactly that set — every
filter state stays reproducible as a URL (§2 #7). A value already among the
active filters toggles off: the link *removes* it instead of adding it.

The funding-request list is reached through the page's one global link
(``list_view_url``), which carries the same facet params — there are no
per-row list links.

Rows grouped by *name* resolve to facet values by name — every model row sharing
the name contributes its id, so the link covers precisely the chart's merged set.
The synthetic rows ("Other", "Unknown", "Unassigned") have no link: the shared
form cannot express their set.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from django.http import HttpRequest

from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import FundingSource
from coda.apps.journals.models import Journal
from coda.apps.listfilters import build_url, params_without
from coda.apps.preferences.models import GlobalPreferences, PreloadedVocabularyProvider
from coda.apps.publishers.models import Publisher
from coda.contexts.statistics.dto import ContractRef, GroupRow
from coda.domain.publication import License, OpenAccessType

_LIST_URL = "fundingrequests:list"

# dimension id -> (facet param, multi-valued facet?)
_FACETS: Mapping[str, tuple[str, bool]] = {
    "institution": ("institution", True),
    "subject_area": ("subject_area", True),
    "publication_type": ("publication_type_concept", True),
    "publication_form": ("publication_form", False),
    "license": ("license", True),
    "open_access_type": ("open_access_type", True),
    "journal": ("journal", True),
    "publisher": ("publisher", True),
    "cost_type": ("cost_type", True),
    "funder": ("funder", True),
    "funding_source": ("funding_source", True),
}

# Dimensions whose chart label is already the facet's accepted value.
_IDENTITY_DIMENSIONS = frozenset({"publication_form", "cost_type"})


def facet_param_names(dimension_id: str) -> tuple[str, ...]:
    """The shared-form GET params reproducing a dimension's chart set (§2 #7).

    The ``contract`` facet only reproduces a row with both params; a dimension
    without a facet yields ``()`` — the completeness test in tests/reporting
    pins that no dimension ever reaches that case.
    """
    if dimension_id == "contract":
        return ("contract_name", "contract_year")
    facet = _FACETS.get(dimension_id)
    return () if facet is None else (facet[0],)


@dataclass(frozen=True)
class DrilldownLinks:
    """Resolves chart rows to statistics filter links; the per-dimension lookup
    tables are built once per page render."""

    request: HttpRequest
    _region_url_name: str
    _by_name: Mapping[str, dict[str, list[str]]]

    @classmethod
    def build(
        cls,
        request: HttpRequest,
        *,
        region_url_name: str,
        vocabularies: PreloadedVocabularyProvider | None = None,
    ) -> "DrilldownLinks":
        if vocabularies is None:
            vocabularies = GlobalPreferences.preloaded()
        return cls(
            request=request, _region_url_name=region_url_name, _by_name=_lookup_tables(vocabularies)
        )

    def link(self, dimension_id: str, row: GroupRow) -> str | None:
        if row.is_other or row.is_unknown or row.is_unassigned:
            return None
        if dimension_id == "contract":
            return self._contract_link(row.ref)
        values = self._facet_values(dimension_id, row.label)
        if not values:
            return None
        param, multi = _FACETS[dimension_id]
        return self._url({param: (values, multi)})

    def _facet_values(self, dimension_id: str, label: str) -> list[str]:
        if dimension_id in _IDENTITY_DIMENSIONS:
            return [label]
        return self._by_name[dimension_id].get(label, [])

    def _contract_link(self, ref: object | None) -> str | None:
        """The row's ref carries its identity: one contract (pk) and the year
        the request attached. Both must filter, or the link would widen the
        chart's set to every year of the contract."""
        if not isinstance(ref, ContractRef):
            return None
        return self._url(
            {
                "contract_name": ([str(ref.pk)], False),
                "contract_year": ([str(ref.year)], False),
            }
        )

    def _url(self, filters: Mapping[str, tuple[list[str], bool]]) -> str:
        params = params_without(self.request.GET, "page")
        for key, (values, multi) in filters.items():
            if multi:
                existing = params.getlist(key)
                if values[0] in existing:
                    # Toggle off: the value is already filtering the page.
                    params.setlist(key, [v for v in existing if v not in values])
                else:
                    params.setlist(key, existing + [v for v in values if v not in existing])
            else:
                current = params.getlist(key)
                params.setlist(key, [] if values[0] in current else values)
        return build_url(self._region_url_name, params)


def list_view_url(request: HttpRequest) -> str:
    """The funding-request list with the page's whole filter set (§2 #7):
    the one bridge from the statistics page into the data behind it. The
    statistics page's own state (tab, compare, resolution) is not a list
    filter."""
    return build_url(_LIST_URL, params_without(request.GET, "page", "tab", "compare", "resolution"))


def _lookup_tables(vocabularies: PreloadedVocabularyProvider) -> dict[str, dict[str, list[str]]]:
    """Chart label -> facet values. Concept-typed dimensions key off the
    configured vocabularies — the page's one pre-loaded provider, not the raw
    concept registry: a row whose concept the shared form would reject as an
    invalid choice must not get a link that silently widens the chart's set
    (§2 #7)."""
    # Keyed by concept id: a concept configured for both vocabularies is one
    # facet value, not two.
    publication_type_concepts = {
        concept.id: concept.name
        for vocabulary in (
            vocabularies.get_article_publication_type_vocabulary(),
            vocabularies.get_monograph_publication_type_vocabulary(),
        )
        for concept in vocabulary.concepts
        if concept.name
    }
    return {
        "institution": _group_pks(Institution.objects.values_list("pk", "name")),
        "journal": _group_pks(Journal.objects.values_list("pk", "title")),
        "publisher": _group_pks(Publisher.objects.values_list("pk", "name")),
        "funder": _group_pks(FundingOrganization.objects.values_list("pk", "name")),
        "funding_source": _group_pks(FundingSource.objects.values_list("pk", "name")),
        "subject_area": {
            concept.name: [str(concept.id)]
            for concept in vocabularies.get_subject_classification_vocabulary().concepts
        },
        "publication_type": _group_pks(
            (str(concept_id), name) for concept_id, name in publication_type_concepts.items()
        ),
        "license": {license.name: [license.value] for license in License},
        "open_access_type": {access.name: [access.value] for access in OpenAccessType},
    }


def _group_pks(rows: Iterable[tuple[object, str]]) -> dict[str, list[str]]:
    """Map each display name to every row id carrying it (pk or concept entity
    id) — a chart merges same-named rows, so the drill-down must select them all."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for pk, name in rows:
        grouped[name].append(str(pk))
    return grouped
