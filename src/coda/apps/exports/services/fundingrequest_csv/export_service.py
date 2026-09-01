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
    "corresponding_author",
    "corresponding_author_affiliation",
    "corresponding_author_affiliation_internal_id",
    "doi",
    "isbn",
    "handle",
    "publishing_state",
    "online_date",
    "print_date",
    "subject_area",
    "subject_area_id",
    "publication_type",
    "publication_type_id",
    "estimated_amount",
    "estimated_currency",
    "payment_method",
    "review_result",
    "review_remarks",
    "decided_funding_amount",
    "decided_funding_currency",
    "labels",
    "external_funding",
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


MONEY_COLUMNS = {
    "estimated_amount",
    "decided_funding_amount",
    "position_amount",
    "tax_rate",
    "funded_amount",
}


def _format_money_value(value: str, key: str, decimal_separator: str) -> str:
    if decimal_separator == "," and key in MONEY_COLUMNS:
        return value.replace(".", ",")
    return value


def _single_line(value: str) -> str:
    return (
        value.replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\u2028", " ")
        .replace("\u2029", " ")
        .replace("\ufeff", "")
    )


def export_fundingrequests_to_csv(
    params: FundingRequestSearchParams,
) -> str:
    # 1. Get funding requests using the shared params
    funding_requests = list(queries.get_funding_requests_for_export(params))

    # 2. Fetch concept ids in a single query to avoid N+1 lookups per funding request
    concept_ids = queries.get_concept_id_lookup(funding_requests)

    # 3. Map to export DTOs
    export_dtos = [
        map_funding_request_to_export_dto(
            fr,
            funding_source=params.funding_source,
            concept_ids=concept_ids,
        )
        for fr in funding_requests
    ]

    # 4. Flatten to CSV rows
    all_rows = []
    for dto in export_dtos:
        rows = flatten_detailed(dto)
        for row in rows:
            all_rows.append(
                {
                    key: _format_money_value(_single_line(value), key, params.decimal_separator)
                    for key, value in row.items()
                }
            )

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
