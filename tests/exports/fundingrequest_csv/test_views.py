import pytest
from django.test import Client
from django.urls import reverse
from datetime import date
from decimal import Decimal

from coda.apps.exports.models import FundingRequestCSVExport
from coda.apps.invoices.models import Position
from tests import modelfactory

PREVIEW_COLUMNS = [
    "request_id",
    "publication_title",
    "doi",
    "contract_name",
    "invoice_number",
    "position_amount",
]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest_csv_empty_export_detail_page__is_opened__context_contains_export_details(
    client: Client,
) -> None:

    export = FundingRequestCSVExport.objects.create(
        name="Test Export",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=0,
    )

    response = client.get(reverse("exports:fundingrequests_csv_detail", args=[export.id]))

    assert response.status_code == 200
    assert "export" in response.context
    assert response.context["export"] == export
    assert "preview_rows" in response.context
    assert "preview_columns" in response.context
    assert response.context["preview_rows"] == []
    assert response.context["preview_columns"] == PREVIEW_COLUMNS


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest_csv_export_detail_page_with_data__is_opened__context_contains_export_details_and_preview_data(
    client: Client,
) -> None:

    export = FundingRequestCSVExport.objects.create(
        name="Test Export with Data",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=100,
    )

    response = client.get(reverse("exports:fundingrequests_csv_detail", args=[export.id]))

    assert response.status_code == 200
    assert "export" in response.context
    assert response.context["export"] == export
    assert "preview_rows" in response.context
    assert "preview_columns" in response.context
    assert len(response.context["preview_rows"]) <= 50
    assert response.context["preview_columns"] == PREVIEW_COLUMNS


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_fundingrequest_csv_export_create_view__is_opened__creates_export_and_redirects_to_detail_page(
    client: Client,
) -> None:

    fundingrequest = modelfactory.fundingrequest(title="Export Creation Test Publication")
    fundingrequest.request_date = date(2024, 3, 5)
    fundingrequest.save()

    invoice = modelfactory.invoice()
    invoice.number = "INV-CREATE-001"
    invoice.date = date(2024, 3, 5)
    invoice.save()

    Position.objects.create(
        invoice=invoice,
        publication=fundingrequest.publication,
        description="Publication charge",
        cost_amount=Decimal("1500.00"),
        cost_currency="EUR",
        cost_type="gold-oa",
        tax_rate=Decimal("0.19"),
        external_position_id="POS-CREATE-001",
    )

    period_start = "2024-01-01"
    period_end = "2024-12-31"
    title = "Funding Request Export Test"

    response = client.post(
        reverse("exports:fundingrequests_csv_create"),
        data={
            "period_start": period_start,
            "period_end": period_end,
            "title": title,
        },
    )

    assert response.status_code == 302
    export = FundingRequestCSVExport.objects.get(name=title)
    assert export is not None
    assert export.filters["period_start"] == period_start
    assert export.filters["period_end"] == period_end
    assert export.record_count == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_fundingrequest_csv_export_delete_view__is_called__deletes_export_and_returns_success_response(
    client: Client,
) -> None:

    export = FundingRequestCSVExport.objects.create(
        name="Export to Delete",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=0,
    )

    response = client.post(reverse("exports:fundingrequests_csv_delete", args=[export.id]))

    assert response.status_code == 200
    with pytest.raises(FundingRequestCSVExport.DoesNotExist):
        FundingRequestCSVExport.objects.get(id=export.id)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_fundingrequest_csv_export_create_view__publication_type_filter__is_stored(
    client: Client,
) -> None:

    title = "Funding Request Export With Publication Type"

    response = client.post(
        reverse("exports:fundingrequests_csv_create"),
        data={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
            "title": title,
            "publication_type": "article",
        },
    )

    assert response.status_code == 302
    export = FundingRequestCSVExport.objects.get(name=title)
    assert export.filters["publication_type"] == "article"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_fundingrequest_csv_export_create_view__contract_filter__is_stored(
    client: Client,
) -> None:
    contract = modelfactory.contract()
    title = "Funding Request Export With Contract"

    response = client.post(
        reverse("exports:fundingrequests_csv_create"),
        data={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
            "title": title,
            "contract_name": str(contract.id),
        },
    )

    assert response.status_code == 302
    export = FundingRequestCSVExport.objects.get(name=title)
    assert export.filters["contract_name"] == str(contract.id)
