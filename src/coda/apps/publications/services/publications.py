from collections.abc import Iterable
from typing import cast

from coda.apps.publications.repositories import payment_repository, publication_repository
from coda.domain.contract import ContractId, ContractYear
from coda.domain.publication import PublicationId
from coda.domain.publication.payment import (
    IndividuallyBilledPublicationPayments,
    PublicationCoveredByContract,
    PublicationPayment,
    PublicationPaymentStatus,
)


def get_payment_status(publication: PublicationId) -> PublicationPaymentStatus:
    contracts = publication_repository.get_contracts_for_publication(publication)
    consolidated_billing = _consolidated_billing_contract(contracts)

    if consolidated_billing:
        return PublicationCoveredByContract(
            contract_id=cast(ContractId, consolidated_billing.contract.id),
            contract_name=consolidated_billing.name,
            contract_year=consolidated_billing.year,
        )

    payments = payment_repository.find_payment(publication)

    if not payments:
        return IndividuallyBilledPublicationPayments(publication)

    return payments


def update_payment(publication_id: PublicationId, publication_payment: PublicationPayment) -> None:
    payment_repository.save_payment(publication_id, publication_payment)


def bulk_update_payments(payment_updates: list[tuple[PublicationId, PublicationPayment]]) -> None:
    """
    Bulk update publication payment statuses for better performance.

    Args:
        payment_updates: List of (publication_id, payment_status) tuples
    """
    payment_repository.bulk_save_payments(payment_updates)


def invoice_deleted(publication_id: PublicationId) -> None:
    payment_repository.delete_payment(publication_id)


def _consolidated_billing_contract(contracts: Iterable[ContractYear]) -> ContractYear | None:
    return next(
        (contract_year for contract_year in contracts if contract_year.uses_consolidated_billing()),
        None,
    )
