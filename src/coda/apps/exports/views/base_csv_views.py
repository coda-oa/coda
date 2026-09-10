import os
from collections.abc import Callable, Iterable
from io import StringIO
from typing import Any, BinaryIO, Protocol, cast

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

CSV_ENCODING = "utf-8-sig"


class _CSVExportInstance(Protocol):
    """Common interface of FundingRequestCSVExport and ContractCSVExport."""

    name: str
    filters: dict[str, str]
    csv_file: FieldFile
    record_count: int
    pk: int

    def delete(
        self, using: str | None = None, keep_parents: bool = False
    ) -> tuple[int, dict[str, int]]: ...

    def save(
        self,
        *,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None: ...


def csv_detail_page(
    request: HttpRequest,
    pk: int,
    *,
    model: type[Model],
    template_name: str,
    preview_columns: list[str],
    applied_filters_builder: Callable[[dict[str, str]], list[AppliedFilter]],
    create_url_name: str,
    redo_url_builder: Callable[[dict[str, Any], str], str] = create_redo_url,
    regen_url_name: str | None = None,
) -> HttpResponse:

    export = get_object_or_404(model, pk=pk)
    export_ = cast(_CSVExportInstance, export)

    if not export_.csv_file or not os.path.exists(export_.csv_file.path):
        return render(
            request,
            template_name,
            {
                "export": export,
                "file_missing": True,
                "preview_columns": preview_columns,
                "preview_rows": [],
                "applied_filters": applied_filters_builder(export_.filters),
                "redo_url": redo_url_builder(export_.filters, create_url_name),
                "regen_url": (reverse(regen_url_name, args=[pk]) if regen_url_name else None),
            },
        )

    csv_file = cast(BinaryIO, export_.csv_file.open("rb"))
    with csv_file:
        preview_df = _create_preview_dataframe(csv_file, preview_columns)

    return render(
        request,
        template_name,
        {
            "export": export,
            "file_missing": False,
            "preview_columns": preview_df.columns,
            "preview_rows": preview_df.rows(),
            "applied_filters": applied_filters_builder(export_.filters),
            "redo_url": redo_url_builder(export_.filters, create_url_name),
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


def save_export_csv_file(export: _CSVExportInstance, csv_content: str) -> int:
    """Store *csv_content* on *export* and return the CSV row count."""
    row_count = pl.read_csv(StringIO(csv_content), separator=";").height
    filename = f"{slugify(export.name) or 'export'}-{export.pk}.csv"

    export.csv_file.save(
        filename,
        ContentFile(csv_content.encode(CSV_ENCODING)),
        save=False,
    )
    export.record_count = row_count
    export.save(update_fields=["csv_file", "record_count"])

    return row_count


def csv_regen_view(
    request: HttpRequest,
    pk: int,
    *,
    model: type[Model],
    generate_csv: Callable[[dict[str, str]], str],
    detail_url_name: str,
) -> HttpResponse:
    export = get_object_or_404(model, pk=pk)
    export_ = cast(_CSVExportInstance, export)

    save_export_csv_file(export_, generate_csv(export_.filters))

    return redirect(detail_url_name, pk=export_.pk)


def csv_download_view(
    pk: int,
    *,
    model: type[Model],
) -> FileResponse | HttpResponse:

    export = get_object_or_404(model, pk=pk)
    export_ = cast(_CSVExportInstance, export)

    if not export_.csv_file or not os.path.exists(export_.csv_file.path):
        return HttpResponse(status=404)

    return FileResponse(export_.csv_file.open("rb"))


def _create_preview_dataframe(csv_file: BinaryIO, preview_columns: list[str]) -> pl.DataFrame:
    return pl.read_csv(csv_file, separator=";", n_rows=50).select(preview_columns)
