from datetime import date
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.core.files.base import ContentFile

from coda.apps.contracts import repository as contract_repository
from coda.apps.exports.models import ContractCSVExport
from coda.contexts.finance.services import invoice_service
from coda.domain.contract import PublisherId
from coda.domain.date import DateRange
from coda.domain.finance.invoice import CreditorId
from coda.domain.finance import invoice_positions
from coda.domain.finance.costtypes import ContractCostType
from coda.domain.finance.invoice_positions import ContractItem
from coda.domain.finance.taxrate import TaxRate
from coda.domain.money import Currency, Money
from coda.domain.publication import JournalId
from tests import domainfactory, modelfactory

PREVIEW_COLUMNS = [
    "contract_name",
    "invoice_number",
    "position_amount",
    "funded_amount",
    "funding_source_name",
]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_csv_empty_export_detail_page__is_opened__context_contains_export_details(
    client: Client,
) -> None:
    csv_content = "contract_name;invoice_number;position_amount;funded_amount;funding_source_name\n"
    csv_file = ContentFile(csv_content, name="empty.csv")

    export = ContractCSVExport.objects.create(
        name="Test Export",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=0,
        csv_file=csv_file,
    )

    response = client.get(reverse("exports:contracts_csv_detail", args=[export.id]))

    assert response.status_code == 200
    assert "export" in response.context
    assert response.context["export"] == export
    assert "preview_rows" in response.context
    assert "preview_columns" in response.context
    assert response.context["preview_rows"] == []
    assert response.context["preview_columns"] == PREVIEW_COLUMNS


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_csv_export_detail_page_with_data__is_opened__context_contains_export_details_and_preview_data(
    client: Client,
) -> None:
    export = ContractCSVExport.objects.create(
        name="Test Export with Data",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=100,
        csv_file=ContentFile(
            (
                b"contract_name;invoice_number;position_amount;funded_amount;funding_source_name\n"
                b"Test Contract;INV-1;100.00;100.00;Budget A\n"
                b"Test Contract;INV-2;200.00;200.00;Budget B\n"
            ),
            name="test_export_with_data.csv",
        ),
    )

    response = client.get(reverse("exports:contracts_csv_detail", args=[export.id]))

    assert response.status_code == 200
    assert "export" in response.context
    assert response.context["export"] == export
    assert "preview_rows" in response.context
    assert "preview_columns" in response.context
    assert len(response.context["preview_rows"]) <= 50
    assert response.context["preview_columns"] == PREVIEW_COLUMNS


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_contract_csv_export_create_view__is_opened__creates_export_and_redirects_to_detail_page(
    client: Client,
) -> None:
    period = DateRange.create(start=date(2024, 1, 1), end=date(2024, 12, 31))
    contract = domainfactory.contract(period=period)
    publisher = modelfactory.publisher()
    journal = modelfactory.journal()
    contract.publishers = [PublisherId(publisher.id)]
    contract.journals = [JournalId(journal.id)]
    contract.id = contract_repository.create(contract)

    contract_year = domainfactory.contract_year(contract)

    creditor = modelfactory.creditor()
    position = invoice_positions.create(
        item=ContractItem(contract_year, cost_type=ContractCostType.Publish),
        cost=Money(Decimal("1000.00"), Currency.EUR),
        tax_rate=TaxRate.from_percentage(19),
        external_position_id="POS-001",
    )
    invoice = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=[position])
    invoice.date = date(2024, 6, 15)
    invoice.id = invoice_service.save(invoice)

    period_start = "2024-01-01"
    period_end = "2024-12-31"
    title = "Contract Export Test"

    response = client.post(
        reverse("exports:contracts_csv_create"),
        data={
            "period_start": period_start,
            "period_end": period_end,
            "title": title,
        },
    )

    assert response.status_code == 302
    export = ContractCSVExport.objects.get(name=title)
    assert export is not None
    assert export.filters["period_start"] == period_start
    assert export.filters["period_end"] == period_end
    assert export.record_count == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_contract_csv_export_delete_view__is_called__deletes_export_and_returns_success_response(
    client: Client,
) -> None:
    export = ContractCSVExport.objects.create(
        name="Export to Delete",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=0,
        csv_file=ContentFile(
            "contract_name;invoice_number;position_amount;funded_amount;funding_source_name",
            name="empty.csv",
        ),
    )

    response = client.post(reverse("exports:contracts_csv_delete", args=[export.id]))

    assert response.status_code == 200
    with pytest.raises(ContractCSVExport.DoesNotExist):
        ContractCSVExport.objects.get(id=export.id)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__contract_csv_detail_page__renders_preview_from_stored_csv_snapshot(
    client: Client,
) -> None:
    export = ContractCSVExport.objects.create(
        name="Stored CSV Export",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=1,
    )
    export.csv_file.save(
        "stored.csv",
        ContentFile(
            (
                b"contract_name;invoice_number;position_amount;funded_amount;funding_source_name\n"
                b"My Contract;INV-001;500.00;500.00;Main Budget\n"
            ),
            name="stored.csv",
        ),
        save=True,
    )

    response = client.get(reverse("exports:contracts_csv_detail", args=[export.id]))

    assert response.status_code == 200
    assert response.context is not None
    assert len(response.context["preview_rows"]) == 1

    preview_rows = response.context["preview_rows"]
    row = preview_rows[0]

    assert row[0] == "My Contract"
    assert row[1] == "INV-001"
    assert row[2] == pytest.approx(500.00)
    assert row[3] == pytest.approx(500.00)
    assert row[4] == "Main Budget"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_contract_csv_export_create_view__payment_status_filter__is_stored(
    client: Client,
) -> None:
    title = "Contract Export With Payment Status"

    response = client.post(
        reverse("exports:contracts_csv_create"),
        data={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
            "title": title,
            "payment_status": "paid",
        },
    )

    assert response.status_code == 302
    export = ContractCSVExport.objects.get(name=title)
    assert export.filters["payment_status"] == "paid"


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_contract_csv_export_create_view__funding_source_filter__is_stored(
    client: Client,
) -> None:
    budget = modelfactory.budget()
    title = "Contract Export With Funding Source"

    response = client.post(
        reverse("exports:contracts_csv_create"),
        data={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
            "title": title,
            "funding_source": str(budget.id),
        },
    )

    assert response.status_code == 302
    export = ContractCSVExport.objects.get(name=title)
    assert export.filters["funding_source"] == str(budget.id)
