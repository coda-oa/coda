import os
import pytest
from django.test import Client
from django.urls import reverse
from datetime import date, timedelta
from django.core.files.base import ContentFile
from django.utils import timezone

from coda.apps.exports.models import FundingRequestCSVExport
from coda.contexts.finance.services import invoice_service
from coda.domain.finance.invoice import CreditorId
from coda.domain.publication.publication import PublicationId
from tests import domainfactory, modelfactory

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

    csv_content = "request_id;publication_title;doi;contract_name;invoice_number;position_amount\n"
    csv_file = ContentFile(csv_content, name="empty.csv")

    export = FundingRequestCSVExport.objects.create(
        name="Test Export",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=0,
        csv_file=csv_file,
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
        csv_file=ContentFile(
            (
                b"request_id;publication_title;doi;contract_name;invoice_number;position_amount\n"
                b"REQ-1;Test Publication;;;INV-1;100.00\n"
                b"REQ-2;Another Publication;;;INV-2;200.00\n"
            ),
            name="test_export_with_data.csv",
        ),
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

    position = domainfactory.publication_position(PublicationId(fundingrequest.publication.id))
    creditor = modelfactory.creditor()
    invoice = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=[position])
    invoice_service.save(invoice)

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
def test_fundingrequest_csv_export_create_view__is_opened__form_offers_decimal_separator_choices(
    client: Client,
) -> None:

    response = client.get(reverse("exports:fundingrequests_csv_create"))

    assert response.status_code == 200
    content = response.content.decode()
    assert 'name="decimal_separator"' in content
    assert ". (English/ISO)" in content
    assert ", (e.g. German)" in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_fundingrequest_csv_export_create_view__decimal_separator_comma__is_stored_in_export_filters(
    client: Client,
) -> None:

    response = client.post(
        reverse("exports:fundingrequests_csv_create"),
        data={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
            "title": "Comma Separator Export",
            "decimal_separator": ",",
        },
    )

    assert response.status_code == 302
    export = FundingRequestCSVExport.objects.get(name="Comma Separator Export")
    assert export.filters["decimal_separator"] == ","


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test_fundingrequest_csv_export_create_view__saved_file__starts_with_utf8_bom(
    client: Client,
) -> None:

    response = client.post(
        reverse("exports:fundingrequests_csv_create"),
        data={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
            "title": "Encoding Test Export",
        },
    )

    assert response.status_code == 302
    export = FundingRequestCSVExport.objects.get(name="Encoding Test Export")
    with export.csv_file.open("rb") as f:
        # b"\xef\xbb\xbf" is the UTF-8 byte order mark (BOM). Excel needs it to
        # detect the file as UTF-8; without it Excel assumes Windows-1252 and
        # garbles umlauts (ä -> Ã¤).
        assert f.read(3) == b"\xef\xbb\xbf"


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
        csv_file=ContentFile(
            "request_id;publication_title;doi;contract_name;invoice_number;position_amount",
            name="empty.csv",
        ),
    )

    response = client.post(reverse("exports:fundingrequests_csv_delete", args=[export.id]))

    assert response.status_code == 200
    with pytest.raises(FundingRequestCSVExport.DoesNotExist):
        FundingRequestCSVExport.objects.get(id=export.id)


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest_csv_detail_page__renders_preview_from_stored_csv_snapshot(
    client: Client,
) -> None:
    export = FundingRequestCSVExport.objects.create(
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
                b"request_id;publication_title;doi;contract_name;invoice_number;position_amount\n"
                b"REQ-1;Stored Publication;;;INV-1;100.00\n"
            ),
            name="stored.csv",
        ),
        save=True,
    )

    response = client.get(reverse("exports:fundingrequests_csv_detail", args=[export.id]))

    assert response.status_code == 200
    assert response.context is not None
    assert len(response.context["preview_rows"]) == 1

    preview_rows = response.context["preview_rows"]

    row = preview_rows[0]

    assert row[0] == "REQ-1"
    assert row[1] == "Stored Publication"
    assert row[4] == "INV-1"
    assert row[5] == pytest.approx(100.00)


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


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest_csv_detail_page__csv_file_missing__shows_metadata_and_file_missing_flag(
    client: Client,
) -> None:
    export = FundingRequestCSVExport.objects.create(
        name="Missing File Export",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=42,
    )
    export.csv_file.save(
        "missing.csv",
        ContentFile(
            b"request_id;publication_title;doi;contract_name;invoice_number;position_amount\n"
            b"REQ-1;Test;;;INV-1;100.00\n"
        ),
        save=True,
    )
    os.remove(export.csv_file.path)

    response = client.get(reverse("exports:fundingrequests_csv_detail", args=[export.id]))

    assert response.status_code == 200
    assert response.context["file_missing"] is True
    assert response.context["export"] == export


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest_csv_detail_page__csv_file_missing__provides_regen_url(
    client: Client,
) -> None:
    export = FundingRequestCSVExport.objects.create(
        name="Missing File Export",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=42,
    )
    export.csv_file.save(
        "missing.csv",
        ContentFile(
            b"request_id;publication_title;doi;contract_name;invoice_number;position_amount\n"
            b"REQ-1;Test;;;INV-1;100.00\n"
        ),
        save=True,
    )
    os.remove(export.csv_file.path)

    response = client.get(reverse("exports:fundingrequests_csv_detail", args=[export.id]))

    assert response.status_code == 200
    assert "regen_url" in response.context
    assert response.context["regen_url"] == reverse(
        "exports:fundingrequests_csv_regen", args=[export.id]
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest_csv_download__csv_file_missing__returns_correct_404_error(
    client: Client,
) -> None:
    export = FundingRequestCSVExport.objects.create(
        name="Missing Download",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=0,
    )
    export.csv_file.save(
        "download_missing.csv",
        ContentFile(
            b"request_id;publication_title;doi;contract_name;invoice_number;position_amount\n"
            b"REQ-1;Test;;;INV-1;100.00\n"
        ),
        save=True,
    )
    os.remove(export.csv_file.path)

    response = client.get(reverse("exports:fundingrequests_csv_download", args=[export.id]))

    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__fundingrequest_csv_regen__called_with_existing_export__regenerates_csv_using_stored_filters(
    client: Client,
) -> None:
    fundingrequest = modelfactory.fundingrequest(title="Regen Test Publication")
    fundingrequest.request_date = date(2024, 3, 5)
    fundingrequest.save()

    position = domainfactory.publication_position(PublicationId(fundingrequest.publication.id))
    creditor = modelfactory.creditor()
    invoice = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=[position])
    invoice_service.save(invoice)

    export = FundingRequestCSVExport.objects.create(
        name="Regen Export",
        filters={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        },
        record_count=0,
    )
    export.csv_file.save(
        "regen.csv",
        ContentFile(
            b"request_id;publication_title;doi;contract_name;invoice_number;position_amount\n"
            b"REQ-1;Old;;;INV-1;100.00\n"
        ),
        save=True,
    )
    os.remove(export.csv_file.path)

    response = client.post(reverse("exports:fundingrequests_csv_regen", args=[export.id]))

    assert response.status_code == 302
    export.refresh_from_db()
    assert export.csv_file
    assert os.path.exists(export.csv_file.path)
    assert export.record_count == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__export_list__is_ordered_by_created_at_descending(client: Client) -> None:
    now = timezone.now()
    older = FundingRequestCSVExport.objects.create(
        name="a_old.csv",
        filters={},
        record_count=0,
    )
    older.created_at = now - timedelta(days=2)
    older.save()
    newer = FundingRequestCSVExport.objects.create(
        name="b_new.csv",
        filters={},
        record_count=0,
    )
    newer.created_at = now
    newer.save()

    response = client.get(reverse("exports:fundingrequests_csv_list"))

    assert response.status_code == 200
    assert [e.name for e in response.context["entities"]] == ["b_new.csv", "a_old.csv"]


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invalid_processing_status_post__creating_export__re_renders_without_creating(
    client: Client,
) -> None:
    response = client.post(
        reverse("exports:fundingrequests_csv_create"),
        data={
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
            "title": "Bad Export",
            "processing_status": ["bogus"],
        },
    )

    assert response.status_code == 200
    assert "form_errors" in response.context
    assert response.context["current_filters"]["processing_status"] == ["bogus"]
    assert FundingRequestCSVExport.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__malformed_date_in_create_post__creating_export__re_renders_without_creating(
    client: Client,
) -> None:
    response = client.post(
        reverse("exports:fundingrequests_csv_create"),
        data={
            "period_start": "01.01.2024",
            "period_end": "2024-12-31",
            "title": "Bad Date Export",
        },
    )

    assert response.status_code == 200
    assert "form_errors" in response.context
    assert FundingRequestCSVExport.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__malformed_date_in_create_post__creating_export__preserves_entered_title_and_dates(
    client: Client,
) -> None:
    response = client.post(
        reverse("exports:fundingrequests_csv_create"),
        data={
            "period_start": "01.01.2024",
            "period_end": "2024-12-31",
            "title": "Keep Me",
        },
    )

    content = response.content.decode()
    assert 'value="Keep Me"' in content
    assert 'value="01.01.2024"' in content
    assert 'value="2024-12-31"' in content


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__missing_period_end_in_create_post__creating_export__re_renders_without_creating(
    client: Client,
) -> None:
    response = client.post(
        reverse("exports:fundingrequests_csv_create"),
        data={"period_start": "2024-01-01", "title": "No End Date"},
    )

    assert response.status_code == 200
    assert "form_errors" in response.context
    assert FundingRequestCSVExport.objects.count() == 0
