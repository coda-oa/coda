from coda.apps.contracts.models import Contract
from coda.apps.exports.services.contract_csv.dtos import (
    ContractCSVExportDto,
    ContractDetailsDto,
    ContractLinkDto,
)
from coda.apps.exports.services.fundingrequest_csv.mappers import map_invoice_to_dto
from coda.apps.invoices.models import Invoice
from coda.contexts.finance.dto.import_dtos import InvoiceImportDto
from coda.domain.finance.invoice import InvoiceId


def map_contract_to_export_dto(
    contract: Contract, matching_invoice_ids: set[InvoiceId] | None = None
) -> ContractCSVExportDto:
    contract_dto = map_contract_to_dto(contract)

    invoices = get_relevant_invoices_for_contract(contract, matching_invoice_ids)

    invoice_dtos: list[InvoiceImportDto] = []
    for invoice in invoices:
        scoped_positions = [
            pos for pos in contract.position_set.all() if pos.invoice_id == invoice.pk
        ]
        invoice_dtos.append(
            map_invoice_to_dto(invoice, invoice_positions=scoped_positions, funding_request=None)
        )

    return ContractCSVExportDto(
        contract=contract_dto,
        invoices=invoice_dtos,
    )


def map_contract_to_dto(contract_model: Contract) -> ContractDetailsDto:

    return ContractDetailsDto(
        name=contract_model.name,
        start_date=contract_model.start_date,
        end_date=contract_model.end_date,
        publishers=[publisher.name for publisher in contract_model.publishers.all()],
        journals=[journal.title for journal in contract_model.journals.all()],
        publication_billing=contract_model.publication_billing,
        active=contract_model.active_status,
        links=[
            ContractLinkDto(type=link.type.name, value=link.value)
            for link in contract_model.links.all()
        ],
    )


def get_relevant_invoices_for_contract(
    contract: Contract, matching_invoice_ids: set[InvoiceId] | None = None
) -> list[Invoice]:
    invoices = {pos.invoice for pos in contract.position_set.all() if pos.invoice is not None}
    if matching_invoice_ids is not None:
        invoices = {inv for inv in invoices if inv.pk in matching_invoice_ids}
    return list(invoices)
