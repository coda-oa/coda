from coda.apps.contracts.models import Contract
from coda.apps.exports.services.contract_csv.dtos import (
    ContractCSVExportDto,
    ContractDetailsDto,
    ContractLinkDto,
)
from coda.apps.exports.services.fundingrequest_csv.mappers import map_invoice_to_dto
from coda.apps.invoices.models import Invoice, Position


def map_contract_to_export_dto(contract: Contract) -> ContractCSVExportDto:
    contract_dto = map_contract_to_dto(contract)

    positions_by_invoice = _positions_by_invoice_of(contract)

    invoice_dtos = [
        map_invoice_to_dto(invoice, invoice_positions=positions, funding_request=None)
        for invoice, positions in positions_by_invoice.items()
    ]

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


def _positions_by_invoice_of(contract: Contract) -> dict[Invoice, list[Position]]:
    grouped: dict[Invoice, list[Position]] = {}
    for position in contract.position_set.select_related("invoice"):
        if position.invoice is not None:
            grouped.setdefault(position.invoice, []).append(position)
    return grouped
