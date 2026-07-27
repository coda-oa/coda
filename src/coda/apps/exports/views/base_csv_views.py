from collections.abc import Callable
from io import StringIO
from typing import Protocol, cast

import polars as pl
from django.contrib import messages
from django.core.files.base import ContentFile
from django.db.models import Model
from django.db.models.fields.files import FieldFile
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify

from coda.apps.exports.services.filter_display import AppliedFilter, create_redo_url


class _CSVExportInstance(Protocol):
    """Common interface of FundingRequestCSVExport and ContractCSVExport."""

    name: str
    filters: dict[str, str]
    csv_file: FieldFile
    record_count: int
    pk: int

    def delete(self) -> None: ...


def csv_detail_page(
    request: HttpRequest,
    pk: int,
    *,
    model: type[Model],
    template_name: str,
    parent_url_name: str,
    preview_columns: list[str],
    applied_filters_builder: Callable[[dict[str, str]], list[AppliedFilter]],
    create_url_name: str,
) -> HttpResponse:

    export = get_object_or_404(model, pk=pk)
    export_ = cast(_CSVExportInstance, export)

    preview_df = _create_preview_dataframe(
        export_.csv_file.open("rb").read().decode("utf-8"), preview_columns
    )

    return render(
        request,
        template_name,
        {
            "export": export,
            "preview_columns": preview_df.columns,
            "preview_rows": preview_df.rows(),
            "applied_filters": applied_filters_builder(export_.filters),
            "redo_url": create_redo_url(export_.filters, create_url_name),
        },
    )


def csv_delete_view(
    request: HttpRequest,
    pk: int,
    *,
    model: type[Model],
    list_url_name: str,
) -> HttpResponse:

    export = get_object_or_404(model, pk=pk)
    export_ = cast(_CSVExportInstance, export)

    export_title = export_.name
    export_.delete()
    messages.success(request, f"CSV export '{export_title}' deleted successfully.")

    response = HttpResponse(status=200)
    response["HX-Redirect"] = reverse(list_url_name)
    return response


def csv_download_view(
    request: HttpRequest,
    pk: int,
    *,
    model: type[Model],
) -> FileResponse:

    export = get_object_or_404(model, pk=pk)
    export_ = cast(_CSVExportInstance, export)
    return FileResponse(export_.csv_file.open("rb"))


def create_csv_export(
    request: HttpRequest,
    model: type[Model],
    *,
    build_filters: Callable[[HttpRequest], dict[str, str]],
    generate_csv: Callable[[dict[str, str]], str],
    detail_url_name: str,
) -> HttpResponse:

    title = request.POST.get("title", "").strip() or "Unnamed CSV Export"

    filters = build_filters(request)
    csv_content = generate_csv(filters)
    row_count = pl.read_csv(StringIO(csv_content), separator=";").height

    export = model._default_manager.create(
        name=title,
        filters=filters,
        record_count=row_count,
    )
    export_ = cast(_CSVExportInstance, export)

    filename = f"{slugify(title) or 'export'}-{export.pk}.csv"

    export_.csv_file.save(
        filename,
        ContentFile(csv_content.encode("utf-8")),
    )

    return redirect(detail_url_name, pk=export.pk)


def _create_preview_dataframe(csv_content: str, preview_columns: list[str]) -> pl.DataFrame:
    return pl.read_csv(StringIO(csv_content), separator=";").select(preview_columns).head(50)
