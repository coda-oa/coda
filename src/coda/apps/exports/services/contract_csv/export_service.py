from coda.apps.exports.services.contract_csv.flatteners import flatten_contract_data
from coda.apps.exports.services.contract_csv.mappers import map_contract_to_export_dto
from coda.apps.exports.services.csv_writer import build_csv_from_rows
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


MONEY_COLUMNS = frozenset({"position_amount", "tax_rate", "funded_amount"})


def export_contract_to_csv(
    params: InvoiceSearchParams,
) -> str:
    contracts = queries.get_contracts_for_export(params)
    export_dtos = [map_contract_to_export_dto(contract) for contract in contracts]
    all_rows = [row for dto in export_dtos for row in flatten_contract_data(dto)]
    return build_csv_from_rows(all_rows, CSV_COLUMNS, MONEY_COLUMNS, params.decimal_separator)
