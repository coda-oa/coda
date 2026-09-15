"""Seed-table outcome columns and pk row ordering.

Seed membership rows are read back in insertion (primary-key) order, so the row order
observed through relation iteration never depends on snapshot content. Freshly created
rows start neutral — not exported, error-free, no XML position — until a generation
run records the actual outcome.
"""

from datetime import date

import pytest

from coda.apps.opencost.models import (
    OpenCostReport,
    OpenCostReportContract,
    OpenCostReportContractInvoice,
    OpenCostReportInvoice,
    OpenCostReportPublication,
)
from tests import modelfactory
from tests.opencost.helpers import create_opencost_report, create_publication_with_invoice


def make_report() -> OpenCostReport:
    return OpenCostReport.objects.create(
        title="Seed outcome report",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
    )


def seeded_publication(report: OpenCostReport, title: str) -> OpenCostReportPublication:
    return OpenCostReportPublication.objects.create(
        report=report,
        publication=modelfactory.publication(title=title),
        title=title,
        publication_type="article",
    )


def seeded_contract(report: OpenCostReport, name: str) -> OpenCostReportContract:
    contract = modelfactory.contract()
    contract.name = name
    contract.save()
    return OpenCostReportContract.objects.create(
        report=report, contract=contract, contract_name=name
    )


@pytest.mark.django_db
def test_publication_queryset_and_relation_iterate_in_id_order() -> None:
    """Out-of-alphabetical insertion order is preserved, not re-sorted by title."""
    report = make_report()
    rows = [seeded_publication(report, title) for title in ("Zebra", "Apple", "Mango")]
    pks = [row.pk for row in rows]
    assert [row.pk for row in OpenCostReportPublication.objects.all()] == pks
    assert [row.pk for row in report.publications.all()] == pks


@pytest.mark.django_db
def test_publication_invoice_queryset_iterates_in_id_order() -> None:
    report = make_report()
    parent = seeded_publication(report, "Umbrella publication")
    rows = [
        OpenCostReportInvoice.objects.create(
            report_publication=parent, invoice=modelfactory.invoice(), invoice_number=number
        )
        for number in ("INV-300", "INV-100", "INV-200")
    ]
    pks = [row.pk for row in rows]
    assert [row.pk for row in OpenCostReportInvoice.objects.all()] == pks
    assert [row.pk for row in parent.invoices.all()] == pks


@pytest.mark.django_db
def test_contract_queryset_and_relation_iterate_in_id_order() -> None:
    report = make_report()
    rows = [seeded_contract(report, name) for name in ("Zeta", "Alpha", "Middle")]
    pks = [row.pk for row in rows]
    assert [row.pk for row in OpenCostReportContract.objects.all()] == pks
    assert [row.pk for row in report.contracts.all()] == pks


@pytest.mark.django_db
def test_contract_invoice_queryset_iterates_in_id_order() -> None:
    report = make_report()
    parent = seeded_contract(report, "Umbrella contract")
    rows = [
        OpenCostReportContractInvoice.objects.create(
            report_contract=parent, invoice=modelfactory.invoice(), invoice_number=number
        )
        for number in ("INV-300", "INV-100", "INV-200")
    ]
    pks = [row.pk for row in rows]
    assert [row.pk for row in OpenCostReportContractInvoice.objects.all()] == pks
    assert [row.pk for row in parent.invoices.all()] == pks


@pytest.mark.django_db
def test_freshly_created_seed_rows_have_neutral_outcome_defaults() -> None:
    report = make_report()
    publication = seeded_publication(report, "Quiet publication")
    publication_invoice = OpenCostReportInvoice.objects.create(
        report_publication=publication, invoice=modelfactory.invoice()
    )
    contract = seeded_contract(report, "Quiet contract")
    contract_invoice = OpenCostReportContractInvoice.objects.create(
        report_contract=contract, invoice=modelfactory.invoice()
    )

    for row in (publication, publication_invoice, contract, contract_invoice):
        row.refresh_from_db()
    assert (publication.exported, publication.had_errors, publication.xml_ordinal) == (
        False,
        False,
        None,
    )
    assert (contract.exported, contract.had_errors, contract.xml_ordinal) == (False, False, None)
    assert (
        publication_invoice.exported,
        publication_invoice.had_errors,
        publication_invoice.xml_index,
    ) == (False, False, None)
    assert (
        contract_invoice.exported,
        contract_invoice.had_errors,
        contract_invoice.xml_index,
    ) == (False, False, None)


@pytest.mark.django_db
def test_generated_seed_rows_carry_neutral_defaults_through_the_legacy_write_path() -> None:
    """Generation writes seed rows without touching the outcome columns — every new
    column has a database-level default, so no insert hits a NOT NULL violation."""
    publication = modelfactory.publication(title="Generated publication")
    create_publication_with_invoice(publication, invoice_number="INV-GEN-0001")

    report = create_opencost_report()

    publications = list(report.publications.all())
    assert len(publications) == 1
    invoices = list(publications[0].invoices.all())
    assert len(invoices) == 1
    pub_row = publications[0]
    invoice_row = invoices[0]
    assert (pub_row.exported, pub_row.had_errors, pub_row.xml_ordinal) == (False, False, None)
    assert (invoice_row.exported, invoice_row.had_errors, invoice_row.xml_index) == (
        False,
        False,
        None,
    )
