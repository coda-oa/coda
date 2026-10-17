"""
Context:
Changing the contract period introduces consistency challenges in other contexts.
Both invoices and publications can reference contract years. If the period
changes so that the referenced contract years are outside the new boundaries the
contract years must stay the same, but we should receive warnings
"""

from datetime import date

import pytest

from coda.apps.contracts import repository as contract_repository
from coda.apps.invoices import repository as invoice_repository
from coda.apps.publications.repositories import publication_repository
from coda.contexts.finance.services.invoice_import import save
from coda.domain.date import DateRange
from coda.domain.finance.invoice import CreditorId
from coda.domain.publication.publication import JournalId
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__contract_period_changed__invoice_referencing_contract_year_keeps_old_data() -> None:
    contract = domainfactory.contract(period=DateRange(date(2024, 1, 1), date(2025, 1, 1)))
    contract.id = contract_repository.create(contract)

    expected_position = domainfactory.contract_position(contract.in_first_year())

    creditor = CreditorId(modelfactory.creditor().pk)
    invoice = domainfactory.invoice(creditor=creditor)
    invoice.positions = [expected_position]
    invoice.id = save(invoice)

    contract.period = DateRange(date(2025, 1, 1), date(2026, 1, 1))
    contract_repository.update(contract)

    actual = invoice_repository.get_by_id(invoice.id)
    assert tuple(invoice.positions) == tuple(actual.positions)


@pytest.mark.django_db
def test__contract_period_changed__publication_referencing_contract_year_keeps_data() -> None:
    contract = domainfactory.contract(period=DateRange(date(2024, 1, 1), date(2025, 1, 1)))
    contract.id = contract_repository.create(contract)

    journal = JournalId(modelfactory.journal().pk)
    publication = domainfactory.publication(journal=journal)
    publication.contracts = (contract.in_first_year(),)
    publication.id = publication_repository.create(publication)

    contract.period = DateRange(date(2025, 1, 1), date(2026, 1, 1))
    contract_repository.update(contract)

    actual = publication_repository.get_by_id(publication.id)
    assert actual.contracts == publication.contracts
