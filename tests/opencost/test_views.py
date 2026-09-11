from datetime import date

import pytest
from django.contrib.messages import get_messages
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from coda.apps.opencost.models import OpenCostReport
from coda.apps.preferences.models import GlobalPreferences
from tests import modelfactory
from tests.opencost.helpers import (
    create_contract_with_identifiers,
    create_contract_with_invoice,
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
def test__generate_without_home_institution__fails_without_creating_a_report(
    client: Client,
) -> None:
    GlobalPreferences.objects.all().delete()

    response = client.post(
        reverse("opencost:generate_submit"),
        data={
            "title": "No Institution Report",
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
        },
    )

    assert response.status_code == 302
    assert OpenCostReport.objects.count() == 0
    flashes = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("No home institution is set" in m for m in flashes)
    assert any("was not generated" in m for m in flashes)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__generate_with_home_institution__warns_only_about_actual_issues(
    client: Client,
) -> None:
    prefs, _ = GlobalPreferences.objects.get_or_create()
    prefs.home_institution = modelfactory.institution()
    prefs.save()

    response = client.post(
        reverse("opencost:generate_submit"),
        data={
            "title": "Institution Report",
            "period_start": "2024-01-01",
            "period_end": "2024-01-31",
        },
    )

    assert response.status_code == 302
    flashes = [str(m) for m in get_messages(response.wsgi_request)]
    assert not any("No home institution is set" in m for m in flashes)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__download_xml_with_unreportable_contract__warns_about_the_exclusion(
    client: Client,
) -> None:
    fr = modelfactory.fundingrequest(title="Publication For Download")
    create_publication_with_invoice(
        fr.publication,
        invoice_date=date(2024, 6, 1),
        invoice_number="INV-DL-001",
    )
    contract = create_contract_with_identifiers(name="Undated Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()
    report_contract = report.contracts.first()
    assert report_contract is not None
    report_contract.participation_from = None
    report_contract.save()

    response = client.get(reverse("opencost:download", args=[report.id]))

    assert response.status_code == 200
    assert b"Undated Agreement" not in response.content

    flash = [str(message) for message in get_messages(response.wsgi_request)]
    assert len(flash) == 1
    assert "Undated Agreement" in flash[0]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__report_detail__issues_panel_is_not_inlined_and_the_page_stays_cheap(
    client: Client,
) -> None:
    contract = create_contract_with_identifiers(name="Undated Agreement")
    create_contract_with_invoice(contract)

    report = create_opencost_report()
    report_contract = report.contracts.first()
    assert report_contract is not None
    report_contract.participation_from = None
    report_contract.save()

    with CaptureQueriesContext(connection) as ctx:
        response = client.get(reverse("opencost:detail", args=[report.id]))

    assert response.status_code == 200
    content = response.content.decode()
    # the panel is no longer server-rendered into the detail page
    assert "Data Completeness Issues" not in content
    # the fragment is deferred to the hx-get load instead
    assert f'hx-get="/opencost/{report.id}/issues/"' in content
    assert len(ctx.captured_queries) <= 15
