from io import StringIO
import polars as pl

from coda.apps.exports.services.contract_csv.flatteners import flatten_contract_data
from coda.apps.exports.services.contract_csv.mappers import map_contract_to_export_dto
from coda.apps.invoices.invoice_query import InvoiceSearchParams
from coda.apps.exports.services.contract_csv import queries

CSV_COLUMNS = [
    "contract_name",
    "start_date",
    "end_date",
    "publishers",
    "journals",
    "publication_billing",
    "active_status",
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
    "contract_year",
    "funded_amount",
    "funding_source_name",
    "funding_source_type",
]


def export_contract_to_csv(
    params: InvoiceSearchParams,
) -> str:
    contracts_with_invoices = queries.get_contracts_for_export(params)

    export_dtos = [
        map_contract_to_export_dto(contract_and_invoices)
        for contract_and_invoices in contracts_with_invoices
    ]

    all_rows = []
    for dto in export_dtos:
        rows = flatten_contract_data(dto)
        all_rows.extend(rows)

    if not all_rows:
        schema = {column: pl.String for column in CSV_COLUMNS}
        df = pl.DataFrame(schema=schema)
    else:
        df = pl.DataFrame(all_rows)

    buffer = StringIO()
    df.write_csv(buffer, separator=";")

    return buffer.getvalue()
