from datetime import date
from io import StringIO
from typing import Any

import polars as pl

from coda.apps.exports.services.fundingrequest_csv import queries
from coda.apps.exports.services.fundingrequest_csv.flatteners import flatten_detailed
from coda.apps.exports.services.fundingrequest_csv.mappers import map_funding_request_to_export_dto

CSV_COLUMNS = [
    "legacy_request_id",
    "request_date",
    "publication_title",
    "publication_kind",
    "eissn",
    "journal_name",
    "publisher_name",
    "license",
    "open_access_type",
    "authors",
    "doi",
    "isbn",
    "handle",
    "publishing_state",
    "online_date",
    "print_date",
    "subject_area",
    "publication_type",
    "estimated_amount",
    "estimated_currency",
    "payment_method",
    "review_result",
    "review_remarks",
    "decided_funding_amount",
    "decided_funding_currency",
    "labels",
    "project_id",
    "project_name",
    "funding_organization",
    "invoice_number",
    "invoice_date",
    "creditor",
    "invoice_status",
    "invoice_currency",
    "invoice_comment",
    "external_invoice_id",
    "position_amount",
    "tax_rate",
    "cost_type",
    "position_type",
    "request_id",
    "legacy_position_request_id",
    "contract_name",
    "contract_year",
    "position_description",
    "funded_amount",
    "funding_source_name",
    "funding_source_type",
]


def export_fundingrequests_to_csv(
    period_start: date,
    period_end: date,
    **filter_params: Any,
) -> str:

    # 1. Get funding requests for the specified period (using queries.py)
    funding_requests = queries.get_funding_requests_for_export(
        period_start=period_start,
        period_end=period_end,
        **filter_params,
    )
    # 2. Map to export DTOs (using mappers.py)
    invoice_filter_params = {
        "invoice_date_start": filter_params.get("invoice_date_start"),
        "invoice_date_end": filter_params.get("invoice_date_end"),
        "invoice_status": filter_params.get("invoice_status"),
        "invoice_creditor": filter_params.get("invoice_creditor", ""),
        "funding_source": filter_params.get("funding_source"),
    }

    export_dtos = [
        map_funding_request_to_export_dto(fr, **invoice_filter_params) for fr in funding_requests
    ]

    # 3. Flatten to CSV rows (using flatteners.py)
    all_rows = []
    for dto in export_dtos:
        rows = flatten_detailed(dto)
        all_rows.extend(rows)

    # 4. Build Polars DataFrame from rows
    if not all_rows:
        schema = {column: pl.String for column in CSV_COLUMNS}
        df = pl.DataFrame(schema=schema)
    else:
        df = pl.DataFrame(all_rows)

    # 5. Write CSV to StringIO with separator semicolon
    buffer = StringIO()
    df.write_csv(buffer, separator=";")

    return buffer.getvalue()
