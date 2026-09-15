from datetime import date

import pytest
from django.contrib.messages import get_messages
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from coda.apps.opencost.models import OpenCostReport
from coda.apps.opencost.report_service import generate_report
from coda.apps.preferences.models import GlobalPreferences
from tests import modelfactory
from tests.opencost.helpers import (
    create_contract_with_identifiers,
    create_contract_with_invoice,
    create_institution_with_identifiers,
    create_opencost_report,
    create_publication_with_invoice,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invalid_open_access_type__generating_report__re_renders_without_creating(
    client: Client,
) -> None:
    response = client.post(
        reverse("opencost:generate_submit"),
        data={
            "title": "Broken Report",
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
            "open_access_type": ["bogus"],
        },
    )

    assert response.status_code == 200
    assert "form_errors" in response.context
    assert response.context["current_filters"]["open_access_type"] == ["bogus"]
    assert OpenCostReport.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__valid_minimal_generate_post__generating_report__creates_report(client: Client) -> None:
    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = modelfactory.institution()
    prefs.save()

    response = client.post(
        reverse("opencost:generate_submit"),
        data={
            "title": "Valid Report",
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
        },
    )

    assert response.status_code == 302
    assert OpenCostReport.objects.get(title="Valid Report").filters == {
        "period_start": "2024-01-01",
        "period_end": "2024-01-31",
    }


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invalid_open_access_type__generating_report__preserves_entered_title_and_dates(
    client: Client,
) -> None:
    response = client.post(
        reverse("opencost:generate_submit"),
        data={
            "title": "Keep Me",
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
            "open_access_type": ["bogus"],
        },
    )

    content = response.content.decode()
    assert 'value="Keep Me"' in content
    assert 'value="2024-01-01"' in content
    assert 'value="2024-01-31"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__generate_without_home_institution__creates_a_report_that_exports_nothing(
    client: Client,
) -> None:
    """A missing preference is an issue the report states, not a refusal to run.

    Nothing can name an institution without it, so every item is considered and left out; the
    reader is sent to the report to be told that, instead of back to a form that silently kept
    the filters they had just typed.
    """
    GlobalPreferences.objects.all().delete()
    fr = modelfactory.fundingrequest(title="Publication with no institution to name")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 1, 15),
        invoice_number="INV-VIEW-NOINST",
    )

    response = client.post(
        reverse("opencost:generate_submit"),
        data={
            "title": "No Institution Report",
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
        },
    )

    assert response.status_code == 302
    report = OpenCostReport.objects.get(title="No Institution Report")
    assert report.publications.count() == 1
    assert report.publications.get().exported is False
    assert report.xml_content == ""
    assert report.has_issues() is True

    flashes = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("has 1 error" in m for m in flashes)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__generate_with_home_institution__exports_its_item_and_reports_no_issues(
    client: Client,
) -> None:
    """The same run with a home institution configured exports what it covers, without warning."""
    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = create_institution_with_identifiers(
        name="Reporting University",
        ror="https://ror.org/view1",
    )
    prefs.save()
    fr = modelfactory.fundingrequest(title="Clean Publication")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 1, 15),
        invoice_number="INV-VIEW-CLEAN",
    )

    response = client.post(
        reverse("opencost:generate_submit"),
        data={
            "title": "Institution Report",
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
        },
    )

    assert response.status_code == 302
    report = OpenCostReport.objects.get(title="Institution Report")
    assert report.publications.get().exported is True
    assert report.has_issues() is False

    flashes = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("generated successfully" in m for m in flashes)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__download_xml__serves_the_stored_document_without_any_flash(client: Client) -> None:
    fr = modelfactory.fundingrequest(title="Publication For Download")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-DL-001",
    )
    contract = create_contract_with_identifiers(name="Undated Agreement", esac="ESAC-UNDATED")
    contract.start_date = None
    contract.end_date = None
    contract.save()
    create_contract_with_invoice(contract)

    report = create_opencost_report()

    response = client.get(reverse("opencost:download", args=[report.id]))

    assert response.status_code == 200
    stored = OpenCostReport.objects.get(pk=report.pk).xml_content
    assert response.content.decode() == stored
    assert response["Content-Disposition"] == (
        f'attachment; filename="{report.title}_{report.id}_'
        f'{report.generated_at.strftime("%Y%m%d")}.xml"'
    )
    # the undated contract stayed out of the document...
    assert b"Undated Agreement" not in response.content
    # ...and its stored error-level issue no longer triggers a download-time flash
    assert report.get_issue_counts()["errors"] == 1
    flash = [str(message) for message in get_messages(response.wsgi_request)]
    assert flash == []


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__download_empty_xml__redirects_with_reasons_from_the_stored_issues(
    client: Client,
) -> None:
    GlobalPreferences.objects.all().delete()
    fr = modelfactory.fundingrequest(title="Unexportable Publication")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-DL-EMPTY-001",
    )

    report = generate_report(
        title="All Excluded Report",
        filters={"period_start": "2024-01-01", "period_end": "2024-12-31"},
    )
    assert report.xml_content == ""

    response = client.get(reverse("opencost:download", args=[report.id]))

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("opencost:list")
    flash = [str(message) for message in get_messages(response.wsgi_request)]
    assert len(flash) == 1
    assert "No file was downloaded" in flash[0]
    assert "Unexportable Publication" in flash[0]
    assert "it has no institution name or identifier" in flash[0]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__download_empty_xml_without_issues__says_there_is_nothing_to_export(
    client: Client,
) -> None:
    report = OpenCostReport.objects.create(
        title="Hollow Report",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
    )

    response = client.get(reverse("opencost:download", args=[report.id]))

    assert response.status_code == 302
    flash = [str(message) for message in get_messages(response.wsgi_request)]
    assert flash == [
        "No data to export — the report has no publications or contracts to transform."
    ]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__regenerate__GET__is_rejected(client: Client) -> None:
    report = create_opencost_report(title="Readonly Regenerate Report")

    response = client.get(reverse("opencost:regenerate", args=[report.id]))

    assert response.status_code == 405


@pytest.mark.django_db
def test__regenerate__anonymous__redirects_to_login(client: Client) -> None:
    report = create_opencost_report(title="Anonymous Regenerate Report")

    response = client.post(reverse("opencost:regenerate", args=[report.id]))

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login/")
    assert "next=/opencost/" in response.headers["Location"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__regenerate__flashes_the_new_issue_counts_and_redirects_to_detail(
    client: Client,
) -> None:
    contract = create_contract_with_identifiers(name="Flash Count Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()

    response = client.post(reverse("opencost:regenerate", args=[report.id]))

    # the htmx button posts and the browser navigates on the HX-Redirect header
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == reverse("opencost:detail", args=[report.id])
    flash = [str(message) for message in get_messages(response.wsgi_request)]
    assert len(flash) == 1
    # the ESAC-less contract is one warning - the flash counts what the new run recorded
    assert "regenerated" in flash[0]
    assert "1 warning" in flash[0]
    assert reverse("opencost:detail", args=[report.id]) in flash[0]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__regenerate__broken_run__flashes_the_error_and_still_navigates(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = create_opencost_report(title="Unregenerable Report")

    def explode(_report: OpenCostReport) -> OpenCostReport:
        raise RuntimeError("transform died")

    monkeypatch.setattr("coda.apps.opencost.views.regenerate_report_service", explode)

    response = client.post(reverse("opencost:regenerate", args=[report.id]))

    # the failed run must not strand the htmx button on a response with nowhere to go
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == reverse("opencost:detail", args=[report.id])
    flash = [str(message) for message in get_messages(response.wsgi_request)]
    assert len(flash) == 1
    assert "Error regenerating report" in flash[0] and "transform died" in flash[0]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__report_list__defers_the_xml_artifact(client: Client) -> None:
    create_opencost_report(title="Listed Report")

    response = client.get(reverse("opencost:list"))

    assert response.status_code == 200
    entity = response.context["entities"][0]
    assert "xml_content" in entity.get_deferred_fields()
    # the issue log stays loaded - the badges read it row-locally
    assert "issues" not in entity.get_deferred_fields()


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__report_detail__issues_panel_is_not_inlined_and_the_page_stays_cheap(
    client: Client,
) -> None:
    contract = create_contract_with_identifiers(name="Undated Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()

    with CaptureQueriesContext(connection) as ctx:
        response = client.get(reverse("opencost:detail", args=[report.id]))

    assert response.status_code == 200
    content = response.content.decode()
    # the panel is no longer server-rendered into the detail page
    assert "Data Completeness Issues" not in content
    # the fragment is deferred to the hx-get load instead
    assert f'hx-get="/opencost/{report.id}/issues/"' in content
    assert len(ctx.captured_queries) <= 15
