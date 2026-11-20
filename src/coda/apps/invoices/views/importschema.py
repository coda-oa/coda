"""On-demand JSON schema for the invoice import file.

The schema is generated from the Pydantic import DTOs, so it can never drift
from what the import service actually validates.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.utils.html import escape
from django.views.decorators.http import require_http_methods

from coda.contexts.finance.dto.import_dtos import InvoiceListImportDto


def _schema_json() -> str:
    return json.dumps(InvoiceListImportDto.model_json_schema(), indent=2)


@login_required
@require_http_methods(["GET"])
def import_schema_fragment(request: HttpRequest) -> HttpResponse:
    """Return the schema as escaped text; the import page wraps it in <pre><code>."""
    return HttpResponse(escape(_schema_json()), content_type="text/html")


@login_required
@require_http_methods(["GET"])
def import_schema_download(request: HttpRequest) -> HttpResponse:
    """Return the schema as a downloadable JSON file."""
    return HttpResponse(
        _schema_json(),
        content_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="invoice_import_schema.json"'},
    )
