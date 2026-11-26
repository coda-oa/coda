from io import StringIO

import polars as pl

from coda.apps.exports.services.fundingrequest_csv import queries
from coda.apps.exports.services.fundingrequest_csv.flatteners import flatten_detailed
from coda.apps.exports.services.fundingrequest_csv.mappers import map_funding_request_to_export_dto
from coda.apps.fundingrequests.fundingrequest_query import FundingRequestSearchParams

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

FORMULA_INJECTION_PREFIXES = ("=", "+", "-", "@")


def _neutralize_formula_injection(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            key: (f"'{value}" if value.startswith(FORMULA_INJECTION_PREFIXES) else value)
            for key, value in row.items()
        }
        for row in rows
    ]


def export_fundingrequests_to_csv(
    params: FundingRequestSearchParams,
) -> str:
    # 1. Get funding requests using the shared params
    funding_requests = queries.get_funding_requests_for_export(params)

    # 2. Map to export DTOs
    export_dtos = [
        map_funding_request_to_export_dto(
            fr,
            funding_source=params.funding_source,
        )
        for fr in funding_requests
    ]

    # 3. Flatten to CSV rows
    all_rows = []
    for dto in export_dtos:
        rows = flatten_detailed(dto)
        all_rows.extend(rows)

    # 4. Neutralize leading formula characters to prevent spreadsheet formula injection
    all_rows = _neutralize_formula_injection(all_rows)

    # 5. Build Polars DataFrame from rows
    if not all_rows:
        schema = {column: pl.String for column in CSV_COLUMNS}
        df = pl.DataFrame(schema=schema)
    else:
        df = pl.DataFrame(all_rows)

    # 6. Write CSV to StringIO with separator semicolon
    buffer = StringIO()
    df.write_csv(buffer, separator=";")

    return buffer.getvalue()
