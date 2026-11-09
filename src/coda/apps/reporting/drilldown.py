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
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass

from django.http import HttpRequest

from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.institutions.models import Institution
from coda.apps.invoices.models import FundingSource
from coda.apps.journals.models import Journal
from coda.apps.listfilters import build_url, params_without
from coda.apps.preferences.models import GlobalPreferences, PreloadedVocabularyProvider
from coda.apps.publishers.models import Publisher
from coda.apps.reporting.factcache import DISPLAY_STATE_PARAMS
from coda.contexts.statistics.dimensions import PageFacet, by_id
from coda.contexts.statistics.dto import ContractRef, GroupRow, RowKind
from coda.domain.publication import License, OpenAccessType

_LIST_URL = "fundingrequests:list"


def facet_param_names(dimension_id: str) -> tuple[str, ...]:
    """The shared-form GET params reproducing a dimension's chart set (§2 #7).

    The ``contract`` facet only reproduces a row with both params. A dimension
    without a facet yields ``()`` — the completeness test in tests/reporting
    pins that no dimension ever reaches that case.
    """
    facet = by_id(dimension_id).facet
    if facet is None:
        return ()
    return (facet.param, "contract_year") if dimension_id == "contract" else (facet.param,)


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
        lookups: Collection[str] | None = None,
        prebuilt: Mapping[str, dict[str, list[str]]] | None = None,
    ) -> "DrilldownLinks":
        """``lookups`` narrows the label→value tables to the given facet
        lookup keys (None: all). A page that renders only a subset of the
        dimensions pays only for their tables; ``_facet_values`` touches a
        table exactly when the row's dimension names its lookup, so the set
        must be derived from the rendered dimensions, not guessed.
        ``prebuilt`` merges caller-supplied tables, so a view that already
        loaded the rows pays no second round-trip."""
        if vocabularies is None:
            vocabularies = GlobalPreferences.preloaded()
        prebuilt = prebuilt or {}
        # A lookup name in ``prebuilt`` skips the builder: the caller already
        # loaded those rows, and rebuilding them would repeat the query.
        if lookups is None:
            wanted: Collection[str] | None = [n for n in _TABLE_BUILDERS if n not in prebuilt]
        else:
            wanted = [n for n in _TABLE_BUILDERS if n in lookups and n not in prebuilt]
        return cls(
            request=request,
            _region_url_name=region_url_name,
            _by_name={**_lookup_tables(vocabularies, lookups=wanted), **prebuilt},
        )

    def link(self, dimension_id: str, row: GroupRow) -> str | None:
        if row.kind is not RowKind.VALUE:
            return None
        if dimension_id == "contract":
            return self._contract_link(row.ref)
        return self.label_link(dimension_id, row.label)

    def label_link(self, dimension_id: str, label: str) -> str | None:
        """The link for a bare dimension value, without the row-kind check:
        treemap labels are grouping rows by construction. Contract rows are
        not resolvable from a label — they carry a (pk, year) ref instead, so
        this returns None for them; :meth:`link` routes them to their ref."""
        facet = by_id(dimension_id).facet
        if facet is None:
            return None
        values = self._facet_values(facet, label)
        if not values:
            return None
        return self._url({facet.param: (values, facet.multi)})

    def _facet_values(self, facet: PageFacet, label: str) -> list[str]:
        if facet.identity:
            return [label]
        return self._by_name[facet.lookup].get(label, [])

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
    return build_url(_LIST_URL, params_without(request.GET, *DISPLAY_STATE_PARAMS))


def _publication_type_table(
    vocabularies: PreloadedVocabularyProvider,
) -> dict[str, list[str]]:
    """Chart label -> concept ids. Keyed by concept id: a concept configured
    for both publication-type vocabularies is one facet value, not two."""
    concepts = {
        concept.id: concept.name
        for vocabulary in (
            vocabularies.get_article_publication_type_vocabulary(),
            vocabularies.get_monograph_publication_type_vocabulary(),
        )
        for concept in vocabulary.concepts
        if concept.name
    }
    return _group_pks((str(concept_id), name) for concept_id, name in concepts.items())


#: Lookup key -> how to build its label→value table. Registry order is build
#: order, and the page's query budget counts on it. The keys are exactly the
#: ``PageFacet.lookup`` values of the facetable dimensions (pinned by
#: ``test__lookup_tables__keys_match_facet_lookups``). ``_facet_values`` indexes
#: ``_by_name[facet.lookup]``, so a key missing here raises KeyError rather
#: than degrading a drilldown link. Each builder runs only when its lookup is
#: requested, so a tab-scoped page pays for its dimensions' tables and nothing
#: else.
_TABLE_BUILDERS: Mapping[str, Callable[[PreloadedVocabularyProvider], dict[str, list[str]]]] = {
    "institution": lambda v: _group_pks(
        Institution.objects.values_list("pk", Institution.facet_label_field)
    ),
    "journal": lambda v: _group_pks(Journal.objects.values_list("pk", Journal.facet_label_field)),
    "publisher": lambda v: _group_pks(
        Publisher.objects.values_list("pk", Publisher.facet_label_field)
    ),
    "funder": lambda v: _group_pks(
        FundingOrganization.objects.values_list("pk", FundingOrganization.facet_label_field)
    ),
    "funding_source": lambda v: _group_pks(
        FundingSource.objects.values_list("pk", FundingSource.facet_label_field)
    ),
    "subject_area": lambda v: {
        concept.name: [str(concept.id)]
        for concept in v.get_subject_classification_vocabulary().concepts
    },
    "publication_type": _publication_type_table,
    "license": lambda v: {license.name: [license.value] for license in License},
    "open_access_type": lambda v: {access.name: [access.value] for access in OpenAccessType},
}


def _lookup_tables(
    vocabularies: PreloadedVocabularyProvider, *, lookups: Collection[str] | None = None
) -> dict[str, dict[str, list[str]]]:
    """Chart label -> facet values. Concept-typed dimensions key off the
    configured vocabularies — the page's one pre-loaded provider, not the raw
    concept registry: a row whose concept the shared form would reject as an
    invalid choice must not get a link that silently widens the chart's set
    (§2 #7). ``lookups`` builds only the named tables (None: all); unknown
    names are ignored, as they always were."""
    wanted = (
        _TABLE_BUILDERS.keys() if lookups is None else (n for n in _TABLE_BUILDERS if n in lookups)
    )
    return {name: _TABLE_BUILDERS[name](vocabularies) for name in wanted}


def _group_pks(rows: Iterable[tuple[object, str]]) -> dict[str, list[str]]:
    """Map each display name to every row id carrying it (pk or concept entity
    id) — a chart merges same-named rows, so the drill-down must select them all."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for pk, name in rows:
        grouped[name].append(str(pk))
    return grouped
