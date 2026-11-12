"""The drilldown lookup registry's structural contract.

``_facet_values`` indexes ``_by_name[facet.lookup]`` (drilldown.py), so a
dimension whose lookup key is missing from ``_TABLE_BUILDERS`` raises KeyError
on the first chart row without a matching table. A typo therefore surfaces
only at render time of one section. The alignment test catches it at
collection."""

from coda.apps.reporting.drilldown import _TABLE_BUILDERS
from coda.contexts.statistics.dimensions import DIMENSIONS


def test__lookup_tables__keys_match_facet_lookups() -> None:
    """Every facetable, non-identity dimension has exactly one table builder;
    the registry has no orphans.

    ``contract`` is the deliberate exception: its rows carry a ``ContractRef``
    with the (pk, year) identity in the fact data, and ``_contract_link``
    builds the link without a label→value table. Any new dimension that
    resolves rows by name needs its lookup registered here."""
    facetable = {
        dimension.facet.lookup
        for dimension in DIMENSIONS
        if dimension.facet is not None
        and not dimension.facet.identity
        and dimension.facet.lookup != "contract"
    }
    assert set(_TABLE_BUILDERS) == facetable
