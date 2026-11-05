# tests/reporting/test_queries.py

from datetime import date
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import Client
from pytest_django import DjangoAssertNumQueries

from coda.apps.contracts.mappers._domain import ContractDomainMapper
from coda.apps.exports.services.fundingrequest_csv import queries as export_queries
from coda.apps.reporting import dataset, queries
from coda.domain.author import Role
from coda.domain.money import Currency
from tests import domainfactory, modelfactory
from tests.reporting import helpers
from tests.reporting.test_page import goto, seed


@pytest.mark.django_db
def test__requests_outside_the_period__fetch_requests__returns_only_requests_in_the_period() -> (
    None
):
    fr_march = modelfactory.fundingrequest(title="March FR")
    fr_march.request_date = date(2026, 3, 15)
    fr_march.save()
    fr_april = modelfactory.fundingrequest(title="April FR")
    fr_april.request_date = date(2026, 4, 15)
    fr_april.save()

    results = list(queries.fetch_requests(helpers.criteria()))

    assert results == [fr_march]


@pytest.mark.django_db
def test__populated_requests__fetch_and_build_facts__reads_facts_without_extra_queries(
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """The whole fact set comes out of the statistics fetch graph, with no N+1."""
    institution = modelfactory.institution()
    fr_1 = helpers.request("Populated one")
    helpers.corresponding_author(fr_1, institution.pk)
    helpers.with_concepts(fr_1)
    helpers.with_attached_contract(fr_1)
    publisher_budget = helpers.budget("Publisher Budget")
    gold = helpers.position(fr_1.publication_id, Decimal("1000.00"), Decimal("0.19"))
    gold.assign_funding(publisher_budget, Decimal("1000.00"))
    usd = helpers.position(
        fr_1.publication_id, Decimal("100.00"), Decimal("0.00"), currency=Currency.USD
    )
    helpers.invoice([gold, usd], conversions={Currency.EUR: Decimal("1.2500")})

    fr_2 = helpers.request("Populated two")
    publication_position = helpers.position(fr_2.publication_id, Decimal("500.00"), Decimal("0.00"))
    contract = ContractDomainMapper.map(modelfactory.contract())
    helpers.invoice(
        [
            publication_position,
            domainfactory.contract_position(domainfactory.contract_year(contract)),
            domainfactory.free_position(),
        ]
    )

    with django_assert_num_queries(9):
        facts = helpers.facts()

    assert len(facts) == 2


@pytest.mark.django_db
def test__populated_requests__stats_fetch_and_export_fetch__build_equal_facts() -> None:
    """The statistics page and the CSV export share the row set (one criteria
    pass) but not the prefetch graph: the statistics fetch loads only what
    ``build_facts`` reads. This pins the divergence — facts through either
    shape must be identical, or the shapes have drifted."""
    institution = modelfactory.institution()
    fr_1 = helpers.request("Rich one")
    helpers.corresponding_author(fr_1, institution.pk)
    co_author = modelfactory.author()
    co_author.publication = fr_1.publication
    co_author.roles = Role.CO_AUTHOR.name
    co_author.save()
    helpers.with_concepts(fr_1)
    helpers.with_attached_contract(fr_1)
    publisher_budget = helpers.budget("Publisher Budget")
    gold = helpers.position(fr_1.publication_id, Decimal("1000.00"), Decimal("0.19"))
    gold.assign_funding(publisher_budget, Decimal("1000.00"))
    library = helpers.split_source(institution.pk, "Library")
    usd = helpers.position(
        fr_1.publication_id, Decimal("100.00"), Decimal("0.00"), currency=Currency.USD
    )
    usd.assign_funding(library, Decimal("40.00"))
    helpers.invoice([gold, usd], conversions={Currency.EUR: Decimal("1.2500")})

    fr_2 = helpers.request("Bare two")
    publication_position = helpers.position(fr_2.publication_id, Decimal("500.00"), Decimal("0.00"))
    publication_position.assign_funding(publisher_budget, Decimal("200.00"))
    helpers.invoice([publication_position])

    stats_facts = sorted(helpers.facts(), key=lambda fact: fact.request_id)
    export_qs = export_queries.fetch_funding_requests(helpers.criteria())
    export_facts = sorted(
        dataset.build_facts(export_qs, Currency.EUR), key=lambda fact: fact.request_id
    )

    assert stats_facts == export_facts


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__reporting_page__render__fits_a_fixed_query_budget(
    client: Client, django_assert_num_queries: DjangoAssertNumQueries
) -> None:
    """The render's cost is fixed per view: the fact graph, the rail's facet
    choice lists, exactly one round-trip for the configured vocabularies (the
    form and the drill-down share the page's one pre-loaded provider) and the
    institution treemap's one hierarchy query. The drill-down lookup tables
    are scoped to the active tab's dimensions, so the default (overview) page
    pays for none of them; the venue tab's two tables are the worst case.
    The fact cache answers a repeat request without the fact graph (covered
    in test_factcache); these budgets measure the cold path, so the cache
    is cleared first."""
    seed()

    cache.clear()
    with django_assert_num_queries(32):
        assert goto(client).status_code == 200

    cache.clear()
    with django_assert_num_queries(29):
        assert goto(client, tab="venues").status_code == 200
