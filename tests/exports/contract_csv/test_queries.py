from datetime import date

import pytest
from coda.apps.exports.services.contract_csv.queries import get_contracts_for_export
from coda.apps.invoices.invoice_query import InvoiceSearchParams
from coda.contexts.finance.services import invoice_service
from coda.domain.contract import ContractYear
from coda.domain.date import DateRange
from coda.domain.finance.invoice import CreditorId, Invoice, PaymentStatus
from tests import domainfactory, modelfactory
from coda.apps.contracts import repository as contract_repository
from tests.exports.helpers import create_invoice_with_contract_position


def _create_invoice_with_status(contract_year: ContractYear, status: PaymentStatus) -> Invoice:
    creditor = modelfactory.creditor()
    creditor_id = CreditorId(creditor.pk)
    position = domainfactory.contract_position(contract_year)
    invoice = domainfactory.invoice(creditor=creditor_id, positions=[position])

    if status == PaymentStatus.Paid:
        invoice.pay()
    elif status == PaymentStatus.Rejected:
        invoice.reject()
    elif status == PaymentStatus.Unpaid:
        invoice.reset_payment()

    invoice.id = invoice_service.save(invoice)
    return invoice


@pytest.mark.django_db
def test__contracts_with_positions__query_for_export_without_filters__returns_all_contracts_with_positions() -> (
    None
):
    contract = domainfactory.contract()
    contract.id = contract_repository.create(contract)
    contract_year = domainfactory.contract_year(contract)
    create_invoice_with_contract_position(contract_year)

    params = InvoiceSearchParams()
    contracts, _ = get_contracts_for_export(params)

    assert len(contracts) == 1
    assert contracts[0].pk == int(contract.id)


@pytest.mark.django_db
def test__contract_without_positions__query_for_export__is_excluded() -> None:
    contract = domainfactory.contract()
    contract.id = contract_repository.create(contract)

    params = InvoiceSearchParams()
    contracts, _ = get_contracts_for_export(params)

    assert len(contracts) == 0


@pytest.mark.django_db
def test__contracts_with_invoices_outside_date_range__query_with_date_range_filter__returns_no_contracts() -> (
    None
):
    contract = domainfactory.contract()
    contract.id = contract_repository.create(contract)
    contract_year = domainfactory.contract_year(contract)
    create_invoice_with_contract_position(contract_year)

    params = InvoiceSearchParams(
        date_range=DateRange(start=date(2020, 1, 1), end=date(2020, 12, 31))
    )
    contracts, _ = get_contracts_for_export(params)

    assert len(contracts) == 0


@pytest.mark.django_db
def test__contracts_with_paid_invoices__query_with_payment_status_filter__returns_only_matching_contracts() -> (
    None
):
    contract = domainfactory.contract()
    contract.id = contract_repository.create(contract)
    contract_year = domainfactory.contract_year(contract)
    _create_invoice_with_status(contract_year, PaymentStatus.Paid)

    params = InvoiceSearchParams(payment_status=PaymentStatus.Paid)
    contracts, _ = get_contracts_for_export(params)

    assert len(contracts) == 1
    assert contracts[0].pk == int(contract.id)


@pytest.mark.django_db
def test__contracts_with_unpaid_invoices__query_with_rejected_filter__excludes_contracts() -> None:
    contract = domainfactory.contract()
    contract.id = contract_repository.create(contract)
    contract_year = domainfactory.contract_year(contract)
    _create_invoice_with_status(contract_year, PaymentStatus.Unpaid)

    params = InvoiceSearchParams(payment_status=PaymentStatus.Rejected)
    contracts, _ = get_contracts_for_export(params)

    assert len(contracts) == 0


@pytest.mark.django_db
def test__multiple_contracts_with_invoices__query_for_export__returns_all_contracts() -> None:
    contract1 = domainfactory.contract()
    contract1.id = contract_repository.create(contract1)
    contract_year1 = domainfactory.contract_year(contract1)
    create_invoice_with_contract_position(contract_year1)

    contract2 = domainfactory.contract()
    contract2.id = contract_repository.create(contract2)
    contract_year2 = domainfactory.contract_year(contract2)
    create_invoice_with_contract_position(contract_year2)

    params = InvoiceSearchParams()
    contracts, _ = get_contracts_for_export(params)

    assert len(contracts) == 2
