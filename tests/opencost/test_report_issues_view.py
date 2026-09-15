import html
import re
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from coda.apps.opencost.services.issues import collect_issues
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


def _fragment_content(client: Client, report_id: int) -> str:
    """GET the issues fragment and return its unescaped text."""
    response = client.get(reverse("opencost:issues", args=[report_id]))
    assert response.status_code == 200
    return html.unescape(response.content.decode())


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__clean_report__issues_fragment__renders_nothing(client: Client) -> None:
    fr = modelfactory.fundingrequest(title="Clean Publication")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-CLEAN-001",
    )
    contract = create_contract_with_identifiers(name="Clean Contract", esac="ESAC-CLEAN")
    create_contract_with_invoice(contract)

    report = create_opencost_report(title="Clean Report")

    content = _fragment_content(client, report.id)

    assert content.strip() == ""
    assert "Data Completeness Issues" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_without_participation_dates__issues_fragment__shows_error_card_and_link(
    client: Client,
) -> None:
    contract = create_contract_with_identifiers(name="Undated Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()
    report_contract = report.contracts.first()
    assert report_contract is not None
    report_contract.participation_from = None
    report_contract.save()

    content = _fragment_content(client, report.id)

    assert "Data Completeness Issues" in content
    assert "Errors (1)" in content
    assert "These records are missing from the XML:" in content
    assert "Undated Agreement" in content
    assert reverse("contracts:detail", kwargs={"pk": contract.pk}) in content
    assert "Open contract" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_without_esac_id__issues_fragment__shows_substitution_warning(
    client: Client,
) -> None:
    contract = create_contract_with_identifiers(name="No ESAC Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()

    content = _fragment_content(client, report.id)

    assert "Warnings (1)" in content
    assert "Data quality notes — these records are in the XML as they are:" in content
    assert "No ESAC ID — the contract is exported with ESAC 'UNKNOWN'." in content
    assert "Open contract" in content
    assert reverse("contracts:detail", kwargs={"pk": contract.pk}) in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publication_without_doi__issues_fragment__shows_substitution_warning(
    client: Client,
) -> None:
    fr = modelfactory.fundingrequest(title="Monograph without DOI")
    fr.publication.links.filter(type__name="DOI").delete()
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-ISSUES-NODOI-001",
    )

    report = create_opencost_report()

    content = _fragment_content(client, report.id)

    assert "No DOI — the publication is exported with title and journal instead." in content
    assert "Open funding request" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publication_without_publisher__issues_fragment__shows_substitution_warning(
    client: Client,
) -> None:
    fr = modelfactory.fundingrequest(title="Publication without publisher")
    fr.publication.links.filter(type__name="DOI").delete()
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-ISSUES-NOPUB-001",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    report_publication.publisher = ""
    report_publication.save()

    content = _fragment_content(client, report.id)

    assert "No publisher — the publication is exported with 'Unknown Publisher'." in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__records_without_institution__issues_fragment__shows_exclusions_with_preferences_link(
    client: Client,
) -> None:
    fr = modelfactory.fundingrequest(title="Publication without institution")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-ISSUES-NOINST-001",
    )
    contract = create_contract_with_identifiers(name="Contract without institution", esac="ESAC-1")
    create_contract_with_invoice(contract)

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    report_publication.institution_name = ""
    report_publication.institution_identifiers.all().delete()
    report_publication.save()
    report_contract = report.contracts.first()
    assert report_contract is not None
    report_contract.institution_name = ""
    report_contract.institution_identifiers.all().delete()
    report_contract.save()

    content = _fragment_content(client, report.id)

    assert "Errors (2)" in content
    assert "Excluded entirely: it has no institution name or identifier." in content
    assert content.count("Open preferences") == 2
    assert reverse("preferences:global_preferences") in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_unmappable_cost_type__issues_fragment__names_the_fallback(
    client: Client,
) -> None:
    fr = modelfactory.fundingrequest(title="Publication with a partial invoice")
    invoice = create_invoice(
        creditor=create_creditor("Cost Type Creditor"),
        invoice_date=date(2024, 6, 1),
        number="INV-ISSUES-PARTIAL-001",
    )
    create_position(
        invoice,
        fr.publication,
        description="APC",
        cost_amount=Decimal("1000.00"),
        cost_type="gold-oa",
    )
    create_position(
        invoice,
        fr.publication,
        description="Surcharge",
        cost_amount=Decimal("200.00"),
        cost_type="gold-oa",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    report_invoice = report_publication.invoices.first()
    assert report_invoice is not None

    positions = sorted(report_invoice.positions.all(), key=lambda position: position.amount)
    positions[0].cost_type = "service fee"
    positions[0].save()

    content = _fragment_content(client, report.id)

    assert "INV-ISSUES-PARTIAL-001" in content
    assert "'service fee'" in content
    assert "The invoice in the XML covers only its remaining positions." in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__publication_excluded_entirely__issues_fragment__reports_it_once_without_title_duplication(
    client: Client,
) -> None:
    fr = modelfactory.fundingrequest(title="Publication excluded from the XML")
    fr.publication.links.filter(type__name="DOI").delete()
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-ISSUES-DROP-001",
    )

    report = create_opencost_report()
    report_publication = report.publications.first()
    assert report_publication is not None
    report_invoice = report_publication.invoices.first()
    assert report_invoice is not None
    position = report_invoice.positions.first()
    assert position is not None
    position.cost_type = "service fee"
    position.save()

    content = _fragment_content(client, report.id)

    assert content.count("Publication excluded from the XML") == 1
    assert (
        "Excluded entirely: Invoice INV-ISSUES-DROP-001 has no positions with a cost type "
        "or currency openCost accepts ('service fee') and was excluded." in content
    )
    # the record is reported once: no DOI advisory beside the exclusion row
    assert "No DOI" not in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__more_than_50_errors__issues_fragment__caps_rows_and_shows_the_true_total(
    client: Client,
) -> None:
    fr = modelfactory.fundingrequest(title="Publication with many partial invoices")
    creditor = create_creditor("Overflow Creditor")
    for n in range(51):
        invoice = create_invoice(
            creditor=creditor,
            invoice_date=date(2024, 6, 1),
            number=f"INV-ISSUES-OVERFLOW-{n:03d}",
        )
        create_position(
            invoice,
            fr.publication,
            cost_amount=Decimal("1000.00"),
            cost_type="gold-oa",
        )
        create_position(
            invoice,
            fr.publication,
            cost_amount=Decimal("200.00"),
            cost_type="service fee",
        )

    report = create_opencost_report()

    content = _fragment_content(client, report.id)

    assert "Errors (51)" in content
    assert content.count("INV-ISSUES-OVERFLOW-") == 50
    assert "… and 1 more." in content
    assert (
        "The rows above repeat the same problem across this report — fix the data "
        "and generate a new report to shrink this list." in content
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__issues_fragment__shows_the_snapshot_stamp(client: Client) -> None:
    contract = create_contract_with_identifiers(name="No ESAC Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()

    content = _fragment_content(client, report.id)

    assert re.search(r"generated \w+\.? \d{1,2}, \d{4}", content)
    assert (
        "Fixing a source record does not change this list: correct the data, "
        "then generate a new report." in content
    )


@pytest.mark.django_db
def test__collect_issues_on_a_loaded_report__stays_within_the_query_budget() -> None:
    fr = modelfactory.fundingrequest(title="Query Count Publication")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-QUERY-001",
    )
    contract = create_contract_with_identifiers(name="Query Count Contract", esac="ESAC-QC")
    create_contract_with_invoice(contract)

    report = create_opencost_report()

    with CaptureQueriesContext(connection) as ctx:
        collect_issues(report)

    # the transform itself must not query: everything it reads is prefetched
    assert len(ctx.captured_queries) <= 20


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__failed_check__issues_fragment__shows_failure_card_without_fake_rows(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = create_opencost_report(title="Failing Check Report")

    def boom(report: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("coda.apps.opencost.services.issues.to_opencost", boom)

    response = client.get(reverse("opencost:issues", args=[report.id]))

    assert response.status_code == 200
    content = html.unescape(response.content.decode())
    assert "Could not check this report" in content
    assert "The data completeness check failed." in content
    assert "Errors (1)" not in content


@pytest.mark.django_db
def test__anonymous_request__issues_fragment__returns_403(client: Client) -> None:
    report = create_opencost_report(title="Anonymous Report")

    response = client.get(reverse("opencost:issues", args=[report.id]))

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__unknown_report__issues_fragment__returns_404(client: Client) -> None:
    response = client.get(reverse("opencost:issues", args=[999999]))

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__download_xml_with_substitutions_only__does_not_claim_that_records_are_left_out(
    client: Client,
) -> None:
    fr = modelfactory.fundingrequest(title="Publication For Substitution Download")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-SUBST-DL-001",
    )
    contract = create_contract_with_identifiers(name="No ESAC Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()

    response = client.get(reverse("opencost:download", args=[report.id]))

    assert response.status_code == 200
    # the contract is exported anyway (with the ESAC placeholder), so the
    # download flash must not announce that records were left out
    flash = [str(message) for message in get_messages(response.wsgi_request)]
    assert flash == []
