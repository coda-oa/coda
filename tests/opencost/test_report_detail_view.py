"""The report detail page: seed rows joined onto the stored document, defended at every join."""

import pytest
from django.db import connection
from django.test import Client
from django.urls import reverse

import opencost
from coda.apps.opencost.report_service import generate_report
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.models._attachedentities import AttachedContract
from tests import modelfactory
from tests.opencost.helpers import (
    create_contract_with_identifiers,
    create_contract_with_invoice,
    create_opencost_report,
    create_publication_with_invoice,
)

FILTERS = {
    "period_start": "2024-01-01",
    "period_end": "2024-12-31",
}


def _detail(client: Client, report_id: int) -> str:
    response = client.get(reverse("opencost:detail", args=[report_id]))
    assert response.status_code == 200
    return response.content.decode()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__all_excluded_report__detail_page__renders_seed_rows_and_issues_without_a_document(
    client: Client,
) -> None:
    """xml_content == "": from_xml is never touched; the rows render from seed columns + issues."""
    GlobalPreferences.objects.all().delete()
    fr = modelfactory.fundingrequest(title="Unexportable Title")
    create_publication_with_invoice(fr.publication, invoice_number="INV-EXCL")

    report = generate_report(title="All Excluded", filters=FILTERS)
    assert report.xml_content == ""

    content = _detail(client, report.id)

    assert "Unexportable Title" in content  # the kept seed column, the only title source left
    assert "Not in XML" in content
    assert "it has no institution name or identifier" in content
    assert f'hx-get="/opencost/{report.id}/issues/"' in content
    assert reverse("opencost:regenerate", args=[report.id]) in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__exported_publication_row__detail_page_shows_xml_values_and_seed_title_publisher(
    client: Client,
) -> None:
    fr = modelfactory.fundingrequest(title="Displayed Publication")
    create_publication_with_invoice(fr.publication, invoice_number="INV-VIS")

    report = create_opencost_report()
    row = report.publications.get(publication=fr.publication)
    assert row.xml_ordinal is not None
    document = opencost.from_xml(report.xml_content)
    assert document.publication is not None
    element = document.publication[row.xml_ordinal]
    xml_doi = element.primary_identifier.doi
    xml_type = element.publication_type.value
    assert xml_doi

    # the snapshot columns the reader no longer consults for exported rows
    row.doi = "STALE-SEED-DOI"
    row.publication_type = "Unmapped Local Thesis"
    row.save()

    content = _detail(client, report.id)

    assert xml_doi in content
    assert "STALE-SEED-DOI" not in content
    assert f"<td>{xml_type}</td>" in content
    assert "Unmapped Local Thesis" not in content
    # Title and Publisher have no other source: they come from the kept seed columns
    assert "Displayed Publication" in content
    assert row.publisher in content
    # the invoice count is read off the parsed document
    assert "View Invoices (1)" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__exported_contract_row__detail_page_shows_xml_normalized_values(client: Client) -> None:
    contract = create_contract_with_identifiers(name="Display Contract")
    create_contract_with_invoice(contract, invoice_number="INV-DISPLAY")

    report = create_opencost_report()
    row = report.contracts.get(contract=contract)
    row.primary_identifier_value = "STALE-SEED-ESAC"
    row.save()

    content = _detail(client, report.id)

    # an ESAC-less contract displays the placeholder the XML actually carries
    assert "<td>UNKNOWN</td>" in content
    assert "STALE-SEED-ESAC" not in content
    assert "Display Contract" in content
    assert "2024-01-01 - 2024-12-31" in content  # participation, from the parsed document
    assert "View Invoices (1)" in content
    home = GlobalPreferences.objects.get().home_institution
    assert home is not None
    assert home.name in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__degraded_publication__detail_page__links_the_issues_panel_and_names_the_contract(
    client: Client,
) -> None:
    """The publication survives via part_of_contract while its only invoice was dropped."""
    contract = create_contract_with_identifiers(name="Cover Contract", esac="ESAC-COVER")
    create_contract_with_invoice(contract, invoice_number="INV-COVER")
    fr = modelfactory.fundingrequest(title="Covered Publication")
    AttachedContract.objects.create(
        contract=contract, publication=fr.publication, contract_year=2024
    )
    create_publication_with_invoice(
        fr.publication, invoice_number="INV-UNUSABLE", cost_type="service fee"
    )

    report = create_opencost_report()
    row = report.publications.get(publication=fr.publication)
    assert (row.exported, row.had_errors) == (True, True)

    content = _detail(client, report.id)

    assert "In XML, with issues" in content
    assert 'href="#issues"' in content
    # the Contract column shows the part_of_contract ESAC the XML names
    assert "ESAC-COVER" in content
    assert "Covered by contract" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__excluded_contract_row__detail_page_shows_the_reason_from_the_issue_log(
    client: Client,
) -> None:
    fr = modelfactory.fundingrequest(title="Sound Publication")
    create_publication_with_invoice(fr.publication, invoice_number="INV-SOUND")
    contract = create_contract_with_identifiers(name="Undated Agreement", esac="ESAC-X")
    contract.start_date = None
    contract.end_date = None
    contract.save()
    create_contract_with_invoice(contract, invoice_number="INV-UNDATED")

    report = create_opencost_report()
    assert report.contracts.get(contract=contract).exported is False

    content = _detail(client, report.id)

    assert "Undated Agreement" in content
    assert "Not in XML" in content
    assert "no participation start and end date" in content
    # the healthy publication still renders from the document
    assert "Sound Publication" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__exported_row_with_out_of_range_ordinal__detail_page_degrades_it_instead_of_failing(
    client: Client,
) -> None:
    fr = modelfactory.fundingrequest(title="Racing Publication")
    create_publication_with_invoice(fr.publication, invoice_number="INV-RACE")

    report = create_opencost_report()
    row = report.publications.get(publication=fr.publication)
    assert row.exported and row.xml_ordinal is not None
    # what a regenerate racing between the report and seed-row queries can leave behind
    row.xml_ordinal = 999
    row.save()

    content = _detail(client, report.id)

    assert "Racing Publication" in content
    assert "Not in XML" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_and_publication_sharing_an_entity_id__detail_page__keeps_their_reasons_apart(
    client: Client,
) -> None:
    # Both CODA tables count from their own sequence, so a publication and a
    # contract can carry the same entity id - the collision the issue join must
    # survive. Aligning the sequences makes the very next rows collide no matter
    # what earlier tests consumed; the transactional test rolls the setval back.
    with connection.cursor() as cursor:
        cursor.execute("select setval('publications_publication_id_seq', 900000)")
        cursor.execute("select setval('contracts_contract_id_seq', 900000)")

    contract = create_contract_with_identifiers(name="Undated Twin", esac="ESAC-TWIN")
    contract.start_date = None
    contract.end_date = None
    contract.save()
    create_contract_with_invoice(contract, invoice_number="INV-TWIN")

    fr = modelfactory.fundingrequest(title="Numerically Convenient Publication")
    assert fr.publication_id == contract.pk  # the collision the join must survive

    create_publication_with_invoice(
        fr.publication, invoice_number="INV-SAME-ID", cost_type="not_a_cost_type"
    )

    report = create_opencost_report()
    assert report.publications.get(publication=fr.publication).exported is False
    assert report.contracts.get(contract=contract).exported is False

    content = _detail(client, report.id)

    assert content.count("no participation start and end date") == 1
    assert content.count("not_a_cost_type") == 1
