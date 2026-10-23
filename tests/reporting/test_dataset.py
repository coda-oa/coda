# tests/reporting/test_dataset.py

from decimal import Decimal

import pytest

from coda.apps.contracts.mappers._domain import ContractDomainMapper
from coda.apps.invoices import funding_source_repository
from coda.apps.publications.models import AttachedContract
from coda.contexts.statistics.dto import ContractRef, FundingSourceRef, InstitutionRef
from coda.domain.author import InstitutionId, Role
from coda.domain.money import Currency
from coda.domain.publication import Authors
from tests import domainfactory, modelfactory
from tests.reporting import helpers


@pytest.mark.django_db
def test__request_with_two_positions_one_assignment_each__build_facts__sums_spend_and_counts_one_publication() -> (
    None
):
    fr = helpers.request("Two positions")
    publisher_budget = helpers.budget("Publisher Budget")
    library_fund = helpers.budget("Library Fund")
    position_a = helpers.position(fr.publication_id, Decimal("1000.00"), Decimal("0.19"))
    position_a.assign_funding(publisher_budget, Decimal("1000.00"))
    position_b = helpers.position(
        fr.publication_id, Decimal("500.00"), Decimal("0.00"), cost_type="other"
    )
    position_b.assign_funding(library_fund, Decimal("500.00"))
    helpers.invoice([position_a, position_b])

    facts = helpers.facts()

    assert len(facts) == 1
    fact = facts[0]
    assert fact.request_id == fr.pk
    assert fact.publication_id == fr.publication_id
    assert fact.paid_out_total == Decimal("1690.00")
    assert dict(fact.paid_out_by_cost_type) == {
        "gold-oa": Decimal("1190.00"),
        "other": Decimal("500.00"),
    }
    assert dict(fact.funded_by) == {
        FundingSourceRef("Publisher Budget"): Decimal("1190.00"),
        FundingSourceRef("Library Fund"): Decimal("500.00"),
    }
    assert fact.unassigned == Decimal("0.00")
    assert fact.has_invoice is True
    assert fact.invoices_without_rate == 0


@pytest.mark.django_db
def test__two_corresponding_authors_at_two_institutions__build_facts__reports_both_institutions() -> (
    None
):
    institution_1 = modelfactory.institution()
    institution_2 = modelfactory.institution()
    helpers.request(
        title="Two institutions",
        authors=Authors(
            [
                domainfactory.author(
                    affiliation=InstitutionId(institution_1.pk),
                    role=Role.CORRESPONDING_AUTHOR,
                ),
                domainfactory.author(
                    affiliation=InstitutionId(institution_2.pk),
                    role=Role.SUBMITTING_CORRESPONDING_AUTHOR,
                ),
            ]
        ),
    )

    fact = helpers.facts()[0]

    assert fact.institutions == (
        InstitutionRef(institution_1.name),
        InstitutionRef(institution_2.name),
    )
    assert fact.no_corresponding_author is False


@pytest.mark.django_db
def test__request_without_corresponding_author__build_facts__marks_fact_incomplete_without_institutions() -> (
    None
):
    institution = modelfactory.institution()
    helpers.request(
        title="No corresponding author",
        authors=Authors(
            [domainfactory.author(affiliation=InstitutionId(institution.pk), role=Role.CO_AUTHOR)]
        ),
    )

    fact = helpers.facts()[0]

    assert fact.no_corresponding_author is True
    assert fact.institutions == ()


@pytest.mark.django_db
def test__publication_position_under_contract_attached_to_publication__build_facts__lists_contract_with_year() -> (
    None
):
    fr = helpers.request("Contract attached to publication")
    contract = modelfactory.contract()
    AttachedContract.objects.create(
        contract=contract, contract_year=2024, publication=fr.publication
    )
    helpers.invoice([helpers.position(fr.publication_id, Decimal("1000.00"), Decimal("0.19"))])

    fact = helpers.facts()[0]

    assert fact.contracts == (ContractRef(pk=contract.pk, name=contract.name, year=2024),)
    assert fact.paid_out_total == Decimal("1190.00")


@pytest.mark.django_db
def test__invoice_without_conversion_rate__build_facts__excludes_amount_and_counts_invoice() -> (
    None
):
    fr = helpers.request("Unconvertible invoice")
    unconvertible = helpers.position(
        fr.publication_id, Decimal("100.00"), Decimal("0.19"), currency=Currency.USD
    )
    unconvertible_invoice = helpers.invoice([unconvertible])
    convertible = helpers.position(fr.publication_id, Decimal("100.00"), Decimal("0.00"))
    helpers.invoice([convertible])

    fact = helpers.facts()[0]

    assert fact.paid_out_total == Decimal("100.00")
    assert fact.invoices_without_rate == 1
    assert fact.unconvertible_invoice_ids == (unconvertible_invoice,)
    assert fact.has_invoice is True


@pytest.mark.django_db
def test__invoice_with_conversion_rate_to_report_currency__build_facts__converts_gross_per_invoice() -> (
    None
):
    fr = helpers.request("Convertible invoice")
    usd_position = helpers.position(
        fr.publication_id, Decimal("100.00"), Decimal("0.19"), currency=Currency.USD
    )
    helpers.invoice([usd_position], conversions={Currency.EUR: Decimal("1.2500")})

    fact = helpers.facts()[0]

    assert fact.paid_out_total == Decimal("148.75")
    assert dict(fact.paid_out_by_cost_type) == {"gold-oa": Decimal("148.75")}
    assert fact.invoices_without_rate == 0


@pytest.mark.django_db
def test__invoice_also_holding_contract_and_free_positions__build_facts__counts_only_publication_position() -> (
    None
):
    fr = helpers.request("Mixed invoice")
    publication_position = helpers.position(fr.publication_id, Decimal("1000.00"), Decimal("0.19"))
    contract = ContractDomainMapper.map(modelfactory.contract())
    helpers.invoice(
        [
            publication_position,
            domainfactory.contract_position(domainfactory.contract_year(contract)),
            domainfactory.free_position(),
        ]
    )

    fact = helpers.facts()[0]

    assert fact.paid_out_total == Decimal("1190.00")
    assert dict(fact.paid_out_by_cost_type) == {"gold-oa": Decimal("1190.00")}
    assert fact.invoices_without_rate == 0


@pytest.mark.django_db
def test__partially_assigned_position__build_facts__keeps_remainder_as_unassigned() -> None:
    fr = helpers.request("Partial assignment")
    institution = modelfactory.institution()
    budget = helpers.budget("Publisher Budget")
    split = domainfactory.split_source(InstitutionId(institution.pk), institution.name)
    split.id = funding_source_repository.create(split)
    position = helpers.position(fr.publication_id, Decimal("1000.00"), Decimal("0.19"))
    position.assign_funding(budget, Decimal("500.00"))
    position.assign_funding(split, Decimal("200.00"))
    helpers.invoice([position])

    fact = helpers.facts()[0]

    assert fact.paid_out_total == Decimal("1190.00")
    assert dict(fact.funded_by) == {
        FundingSourceRef("Publisher Budget"): Decimal("595.00"),
        FundingSourceRef(institution.name): Decimal("238.00"),
    }
    assert fact.unassigned == Decimal("357.00")


@pytest.mark.django_db
def test__article_publication__build_facts__form_is_article() -> None:
    helpers.request("Journal paper")

    assert helpers.facts()[0].publication_form == "article"


@pytest.mark.django_db
def test__monograph_publication__build_facts__form_is_monograph() -> None:
    fr = helpers.request("Monograph")
    fr.publication.article_journal = None
    fr.publication.monograph_publisher = modelfactory.publisher()
    fr.publication.save()

    assert helpers.facts()[0].publication_form == "monograph"


@pytest.mark.django_db
def test__publication_without_journal_or_publisher__build_facts__form_is_unknown() -> None:
    """Neither facet value matches such a publication — ``PublicationFormCriteria``
    excludes it from both forms, so the fact must not claim one (plan §8)."""
    fr = helpers.request("Formless paper")
    fr.publication.article_journal = None
    fr.publication.save()

    assert helpers.facts()[0].publication_form == "unknown"


@pytest.mark.django_db
def test__publication_with_journal_and_monograph_publisher__build_facts__article_wins() -> None:
    """Both facet values match it; the fact is single-valued with article first."""
    fr = helpers.request("Both forms")
    fr.publication.monograph_publisher = modelfactory.publisher()
    fr.publication.save()

    assert helpers.facts()[0].publication_form == "article"
