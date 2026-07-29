from decimal import Decimal

from coda.apps.exports.services.contract_csv.dtos import ContractCSVExportDto, ContractInfoDto
from coda.contexts.finance.dto.import_dtos import (
    ContractPositionImportDto,
    FundingAssignmentImportDto,
    InvoiceImportDto,
)


def flatten_contract_data(dto: ContractCSVExportDto) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for invoice in dto.invoices:
        for position in invoice.positions:
            if not isinstance(position, ContractPositionImportDto):
                continue
            if not position.funding_assignments:
                rows.append(
                    _create_row(dto.contract, invoice, position, funded_amount=position.amount)
                )
            else:
                for assignment in position.funding_assignments:
                    rows.append(
                        _create_row(
                            dto.contract,
                            invoice,
                            position,
                            assignment=assignment,
                            funded_amount=assignment.amount or Decimal("0"),
                        )
                    )

    return rows


def _create_row(
    contract: ContractInfoDto,
    invoice: InvoiceImportDto,
    position: ContractPositionImportDto,
    assignment: FundingAssignmentImportDto | None = None,
    funded_amount: Decimal | None = None,
) -> dict[str, str]:
    link_columns = {link.type.lower(): link.value for link in contract.links}
    return {
        "contract_name": contract.name,
        "start_date": str(contract.start_date) if contract.start_date else "",
        "end_date": str(contract.end_date) if contract.end_date else "",
        "publishers": ", ".join(contract.publishers),
        "journals": ", ".join(contract.journals),
        "publication_billing": contract.publication_billing,
        "active_status": str(contract.active),
        **link_columns,
        "invoice_number": invoice.number,
        "invoice_date": invoice.date.isoformat(),
        "creditor": invoice.creditor,
        "invoice_status": invoice.status.value,
        "invoice_currency": invoice.currency,
        "invoice_comment": invoice.comment or "",
        "external_invoice_id": invoice.external_id or "",
        "position_amount": str(position.amount),
        "tax_rate": str(position.tax_rate),
        "cost_type": position.cost_type.value,
        "contract_year": str(position.contract_year),
        "funded_amount": str(funded_amount) if funded_amount is not None else "",
        "funding_source_name": assignment.name if assignment else "",
        "funding_source_type": assignment.type if assignment else "",
    }
