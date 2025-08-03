from collections.abc import Iterable
from typing import BinaryIO, TextIO, cast

from django.db.models import Q

from coda.apps.contracts import repository as contract_repository
from coda.apps.contracts.models import Contract as ContractModel
from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices import repository
from coda.apps.invoices.importservice.dto import (
    CommonPositionImportDto,
    ContractPositionImportDto,
    FreePositionImportDto,
    InvoiceListImportDto,
    PublicationPositionImportDto,
)
from coda.apps.invoices.models import Creditor, FundingSource
from coda.domain.contract import Contract
from coda.domain.invoice import (
    AnyPosition,
    ContractPosition,
    CreditorId,
    FundingSourceId,
    Invoice,
    Position,
    TaxRate,
)
from coda.domain.money._currency import Currency
from coda.domain.money._money import Money
from coda.domain.publication.publication import PublicationId


def parse_position_dto(
    p: CommonPositionImportDto,
    currency: Currency,
    funding_sources_lookup: dict[str, FundingSourceId],
    request_id_lookup: dict[str, PublicationId],
    contract_lookup: dict[str, Contract],
) -> AnyPosition:
    cost = Money(p.amount, currency)
    tax_rate = TaxRate.from_percentage(p.tax_rate)
    funding_source = funding_sources_lookup[p.funding_source] if p.funding_source else None
    external_id = p.external_id
    position: AnyPosition
    match p:
        case PublicationPositionImportDto():
            id_type = cast(str, p.request_id or p.legacy_request_id)
            position = Position(
                item=request_id_lookup[id_type],
                cost=cost,
                tax_rate=tax_rate,
                funding_source=funding_source,
                external_position_id=external_id,
                cost_type=p.cost_type,
            )
        case ContractPositionImportDto():
            position = ContractPosition(
                item=contract_lookup[p.contract_name].in_year(p.contract_year),
                cost=cost,
                tax_rate=tax_rate,
                funding_source=funding_source,
                external_position_id=external_id,
                cost_type=p.cost_type,
            )
        case FreePositionImportDto():
            position = Position(
                item=p.description,
                cost=cost,
                tax_rate=tax_rate,
                funding_source=funding_source,
                external_position_id=external_id,
                cost_type=p.cost_type,
            )
        case _:
            raise ValueError(f"Unknown position type: {p.type}")

    return position


def import_invoices(json: TextIO | BinaryIO) -> None:
    text_content = json.read()
    dto = InvoiceListImportDto.model_validate_json(text_content)
    creditor_lookup = _bulk_create_creditors(invoice_dto.creditor for invoice_dto in dto.invoices)
    funding_sources_lookup = _bulk_create_funding_sources(
        position.funding_source
        for invoice_dto in dto.invoices
        for position in invoice_dto.positions
    )
    request_id_lookup = _find_publication_ids(
        cast(str, position.request_id or position.legacy_request_id)
        for invoice_dto in dto.invoices
        for position in invoice_dto.positions
        if isinstance(position, PublicationPositionImportDto)
    )
    contract_lookup = _find_contracts(
        position.contract_name
        for invoice_dto in dto.invoices
        for position in invoice_dto.positions
        if isinstance(position, ContractPositionImportDto)
    )
    invoices = [
        Invoice.new(
            number=invoice_dto.number,
            date=invoice_dto.date,
            creditor=creditor_lookup[invoice_dto.creditor],
            status=invoice_dto.status,
            external_invoice_id=invoice_dto.external_id,
            comment=invoice_dto.comment,
            positions=[
                parse_position_dto(
                    p,
                    invoice_dto.currency,
                    funding_sources_lookup,
                    request_id_lookup,
                    contract_lookup,
                )
                for p in invoice_dto.positions
            ],
        )
        for invoice_dto in dto.invoices
    ]
    repository.bulk_create(invoices)


def _find_publication_ids(publications: Iterable[str]) -> dict[str, PublicationId]:
    requests = FundingRequest.objects.filter(
        Q(request_id__in=publications) | Q(legacy_request_id__in=publications)
    ).prefetch_related("publication")

    return {req.request_id: PublicationId(req.publication.id) for req in requests} | {
        req.legacy_request_id: PublicationId(req.publication.id)
        for req in requests
        if req.legacy_request_id
    }


def _find_contracts(contracts: Iterable[str]) -> dict[str, Contract]:
    models = ContractModel.objects.filter(name__in=contracts)
    return {c.name: contract_repository.as_domain_object(c) for c in models}


def _bulk_create_creditors(creditors: Iterable[str]) -> dict[str, CreditorId]:
    existing = Creditor.objects.filter(name__in=creditors)
    existing_map = {c.name: c for c in existing}
    to_create = [Creditor(name=name) for name in creditors if name not in existing_map]
    if to_create:
        created = Creditor.objects.bulk_create(to_create, ignore_conflicts=True)
        existing_map.update({c.name: c for c in created})
    return {name: CreditorId(existing_map[name].id) for name in creditors}


def _bulk_create_funding_sources(funding_sources: Iterable[str]) -> dict[str, FundingSourceId]:
    existing = FundingSource.objects.filter(name__in=funding_sources)
    existing_map = {fs.name: FundingSourceId(fs.id) for fs in existing}
    to_create = [FundingSource(name=name) for name in funding_sources if name not in existing_map]
    if to_create:
        created = FundingSource.objects.bulk_create(to_create, ignore_conflicts=True)
        existing_map.update({fs.name: FundingSourceId(fs.id) for fs in created})

    return existing_map
