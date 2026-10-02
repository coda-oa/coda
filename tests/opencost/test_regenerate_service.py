"""Regeneration: the stored membership re-transformed against current CODA data.

The seed rows are the report's frozen item list; regeneration re-reads everything else live.
These tests pin exactly that contract: fixes flow through, scope never moves.
"""

import re
from datetime import date
from decimal import Decimal

import pytest

import opencost
from coda.apps.contracts.models import ContractLink, ContractLinkType
from coda.apps.opencost.models import OpenCostReport, OpenCostReportInvoice
from coda.apps.opencost.report_service import generate_report, regenerate_report
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models._attachedentities import AttachedContract
from tests import modelfactory
from tests.opencost.helpers import (
    create_contract_with_identifiers,
    create_contract_with_invoice,
    create_creditor,
    create_invoice,
    create_opencost_report,
    create_position,
    create_publication_with_invoice,
)

FILTERS = {
    "period_start": "2024-01-01",
    "period_end": "2024-12-31",
}

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def _generate(title: str = "Regeneration report") -> OpenCostReport:
    return generate_report(title=title, filters=FILTERS)


@pytest.mark.django_db
def test__corrected_esac__regenerate__issue_gone_and_document_names_the_esac() -> None:
    contract = create_contract_with_identifiers(name="No ESAC Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()
    generated_at = report.generated_at
    assert any("No ESAC" in issue["message"] for issue in report.issues)
    original = opencost.from_xml(report.xml_content)
    assert original.contract is not None
    assert original.contract[0].primary_identifier.value == "UNKNOWN"

    esac_type, _ = ContractLinkType.objects.get_or_create(name="ESAC")
    ContractLink.objects.create(contract=contract, type=esac_type, value="ESAC-4711")

    regenerated = regenerate_report(report)

    assert not any("No ESAC" in issue["message"] for issue in regenerated.issues)
    document = opencost.from_xml(regenerated.xml_content)
    assert document.contract is not None
    assert document.contract[0].primary_identifier.value == "ESAC-4711"
    assert regenerated.generated_at > generated_at


@pytest.mark.django_db
def test__position_added_to_pinned_invoice__regenerate__links_and_exports_without_moving_scope() -> (
    None
):
    """A pinned publication's new position on a pinned invoice it had none on before."""
    fr = modelfactory.fundingrequest(title="Pinned Publication")
    own_invoice = create_invoice(
        creditor=create_creditor("Own Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-OWN",
    )
    create_position(own_invoice, fr.publication, cost_amount=Decimal("1000.00"))
    contract = create_contract_with_identifiers(name="Umbrella Contract", esac="ESAC-U")
    contract_invoice = create_invoice(
        creditor=create_creditor("Umbrella Creditor"),
        invoice_date=date(2024, 6, 15),
        number="INV-UMBRELLA",
    )
    create_position(contract_invoice, contract=contract, cost_type="publish")

    report = create_opencost_report()
    pub_row = report.publications.get(publication=fr.publication)
    pub_seed_id, pub_ordinal = pub_row.id, pub_row.xml_ordinal
    contract_row = report.contracts.get(contract=contract)
    contract_seed_id = contract_row.id
    assert pub_ordinal is not None
    assert OpenCostReportInvoice.objects.filter(report_publication=pub_row).count() == 1

    # the fix: the publication was billed on the contract's invoice too, all along
    create_position(contract_invoice, fr.publication, cost_amount=Decimal("300.00"))

    regenerated = regenerate_report(report)

    link_rows = list(OpenCostReportInvoice.objects.filter(report_publication=pub_row))
    assert len(link_rows) == 2, "the missing parent-invoice link row was not inserted"
    new_row = link_rows[-1]
    assert new_row.invoice_id == contract_invoice.id
    assert (new_row.exported, new_row.had_errors, new_row.xml_index) == (True, False, 1)
    # item ids and places never changed
    assert regenerated.publications.get(publication=fr.publication).id == pub_seed_id
    assert regenerated.publications.get(publication=fr.publication).xml_ordinal == pub_ordinal
    assert regenerated.contracts.get(contract=contract).id == contract_seed_id

    document = opencost.from_xml(regenerated.xml_content)
    assert document.publication is not None
    element = document.publication[pub_ordinal]
    invoices = element.cost_data.invoice
    assert invoices is not None
    assert [invoice.invoice_number for invoice in invoices] == [
        "INV-OWN",
        "INV-UMBRELLA",
    ]
    assert invoices[1].amounts_paid.amount_paid[0].amount == Decimal("300.00")

    # a second run inserts nothing further - the unique pair keeps it idempotent
    regenerate_report(regenerated)
    assert OpenCostReportInvoice.objects.filter(report_publication=pub_row).count() == 2


@pytest.mark.django_db
def test__new_matching_publication__regenerate__stays_out_without_a_seed_row() -> None:
    fr = modelfactory.fundingrequest(title="Original Publication")
    create_publication_with_invoice(fr.publication, invoice_number="INV-ORIG")

    report = create_opencost_report()

    late = modelfactory.fundingrequest(title="Late Arrival")
    create_publication_with_invoice(late.publication, invoice_number="INV-LATE")

    regenerated = regenerate_report(report)

    assert not regenerated.publications.filter(publication=late.publication).exists()
    assert "INV-LATE" not in regenerated.xml_content


@pytest.mark.django_db
def test__deleted_pinned_invoice__regenerate__seed_row_cascades_and_document_sheds_it() -> None:
    fr = modelfactory.fundingrequest(title="Twice Billed Publication")
    create_publication_with_invoice(
        fr.publication, invoice_number="INV-STAYS", creditor_name="Staying Creditor"
    )
    doomed, _ = create_publication_with_invoice(
        fr.publication, invoice_number="INV-DOOMED", creditor_name="Doomed Creditor"
    )

    report = create_opencost_report()
    assert "INV-DOOMED" in report.xml_content

    doomed_id = doomed.pk
    doomed.delete()

    regenerated = regenerate_report(report)

    assert not OpenCostReportInvoice.objects.filter(invoice_id=doomed_id).exists()
    assert "INV-DOOMED" not in regenerated.xml_content
    assert "INV-STAYS" in regenerated.xml_content


@pytest.mark.django_db
def test__new_invoice_on_seeded_publication__regenerate__stays_out_because_invoices_are_pinned() -> (
    None
):
    fr = modelfactory.fundingrequest(title="Rebilled Publication")
    create_publication_with_invoice(fr.publication, invoice_number="INV-PINNED")

    report = create_opencost_report()
    pub_row = report.publications.get(publication=fr.publication)

    # a fresh paid in-period invoice for the same publication - corrections as new rows
    # never enter an existing report
    create_publication_with_invoice(
        fr.publication, invoice_number="INV-NEW", creditor_name="New Creditor"
    )

    regenerated = regenerate_report(report)

    assert not OpenCostReportInvoice.objects.filter(
        report_publication=pub_row, invoice__number="INV-NEW"
    ).exists()
    assert "INV-NEW" not in regenerated.xml_content
    assert OpenCostReportInvoice.objects.filter(report_publication=pub_row).count() == 1


@pytest.mark.django_db
def test__position_for_unpinned_publication_on_pinned_invoice__regenerate__stays_out() -> None:
    pinned = modelfactory.fundingrequest(title="Pinned Side Publication")
    invoice, _ = create_publication_with_invoice(pinned.publication, invoice_number="INV-SHARED")

    report = create_opencost_report()

    outsider = modelfactory.fundingrequest(title="Unpinned Outsider")
    create_position(
        invoice, outsider.publication, description="Late position", cost_amount=Decimal("500.00")
    )

    regenerated = regenerate_report(report)

    assert not regenerated.publications.filter(publication=outsider.publication).exists()
    assert "Unpinned Outsider" not in regenerated.xml_content


@pytest.mark.django_db
def test__unset_home_institution__regenerate_after_configuring_it__rows_flip_to_exported() -> None:
    """Service-level heal: the home institution is read live, so setting it is fixable."""
    GlobalPreferences.objects.all().delete()
    fr = modelfactory.fundingrequest(title="Orphan Publication")
    create_publication_with_invoice(fr.publication, invoice_number="INV-HEAL")

    report = _generate(title="Unhealed Report")
    assert report.xml_content == ""
    assert [row.exported for row in report.publications.all()] == [False]
    assert any("institution" in issue["message"] for issue in report.issues)

    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = modelfactory.institution()
    prefs.save()

    regenerated = regenerate_report(report)

    row = regenerated.publications.get(publication=fr.publication)
    assert (row.exported, row.had_errors, row.xml_ordinal) == (True, False, 0)
    assert regenerated.xml_content != ""
    assert not any("institution" in issue["message"] for issue in regenerated.issues)
    # A cleared log must clear the badge counts too: with the log empty the union
    # count properties fall back to the columns, so stale columns would advertise
    # the errors of the run this regeneration just repaired.
    assert regenerated.get_issue_counts() == {"errors": 0, "warnings": 0}
    assert regenerated.has_issues() is False


@pytest.mark.django_db
def test__unchanged_data__regenerating_twice__documents_differ_only_in_group_ids() -> None:
    contract = create_contract_with_identifiers(name="Determinism Deal", esac="ESAC-DET")
    create_contract_with_invoice(contract, invoice_number="INV-DET")

    report = create_opencost_report()

    first = regenerate_report(report).xml_content
    second = regenerate_report(report).xml_content

    assert _UUID.search(first), "the document holds no group ids to normalize"
    assert first != second, "two runs must at least mint fresh group ids"
    assert _UUID.sub("GROUP", first) == _UUID.sub("GROUP", second)


@pytest.mark.django_db
def test__publication_under_two_contracts__regenerate__earliest_year_contract_is_named() -> None:
    fr = modelfactory.fundingrequest(title="Multi Contract Publication")
    create_publication_with_invoice(fr.publication, invoice_number="INV-MULTI")

    newer = create_contract_with_identifiers(name="Newer Deal", esac="ESAC-NEW")
    create_contract_with_invoice(newer, invoice_number="INV-NEWER")
    older = create_contract_with_identifiers(name="Older Deal", esac="ESAC-OLD")
    create_contract_with_invoice(older, invoice_number="INV-OLDER", invoice_date=date(2024, 8, 1))
    AttachedContract.objects.create(contract=newer, publication=fr.publication, contract_year=2024)
    AttachedContract.objects.create(contract=older, publication=fr.publication, contract_year=2023)

    report = create_opencost_report()

    regenerated = regenerate_report(report)

    document = opencost.from_xml(regenerated.xml_content)
    assert document.publication is not None
    part = document.publication[0].cost_data.part_of_contract
    assert part is not None
    assert part.primary_identifier.value == "ESAC-OLD"


@pytest.mark.django_db
def test__regenerate__reports_the_refreshed_row_and_advances_generated_at() -> None:
    fr = modelfactory.fundingrequest(title="Refreshed Publication")
    create_publication_with_invoice(fr.publication, invoice_number="INV-REFRESH")

    report = create_opencost_report()
    generated_at = report.generated_at

    regenerated = regenerate_report(report)

    assert regenerated is report
    assert report.generated_at > generated_at
    assert OpenCostReport.objects.get(pk=report.pk).generated_at == report.generated_at
    assert report.xml_content != ""
    assert OpenCostReportInvoice.objects.filter(
        report_publication__report=report, exported=True, xml_index=0
    ).exists()


@pytest.mark.django_db
def test__regenerate__filters_are_never_consulted() -> None:
    """A report whose stored filters match nothing anymore still regenerates its scope."""
    fr = modelfactory.fundingrequest(title="Frozen Scope Publication")
    create_publication_with_invoice(fr.publication, invoice_number="INV-FROZEN")

    report = create_opencost_report()
    report.filters = {"period_start": "2000-01-01", "period_end": "2000-01-31"}
    report.save(update_fields=["filters"])

    regenerated = regenerate_report(report)

    assert "INV-FROZEN" in regenerated.xml_content
    assert regenerated.publications.count() == 1
    # the stale filters survive untouched - they belong to the reuse-filters UI alone
    assert OpenCostReport.objects.get(pk=report.pk).filters == {
        "period_start": "2000-01-01",
        "period_end": "2000-01-31",
    }
