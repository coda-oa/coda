from collections.abc import Iterable
from typing import cast

from coda.apps.publications.repositories import payment_repository, publication_repository
from coda.domain.contract import ContractId, ContractYear
from coda.domain.finance.invoice import InvoiceId
from coda.domain.publication import PublicationId
from coda.domain.publication.payment import (
    PublicationPayments,
    PaymentEvent,
    PublicationCoveredByContract,
    PublicationPaymentStatus,
)


def _determine_payment_status(
    publication: PublicationId,
    payments: PublicationPayments | None,
    contracts: Iterable[ContractYear],
) -> PublicationPaymentStatus:
    consolidated_billing = _consolidated_billing_contract(contracts)

    if consolidated_billing:
        return PublicationCoveredByContract(
            contract_id=cast(ContractId, consolidated_billing.contract.id),
            contract_name=consolidated_billing.name,
            contract_year=consolidated_billing.year,
        )

    if not payments:
        return PublicationPayments(publication)

    return payments


def get_payment_status(publication: PublicationId) -> PublicationPaymentStatus:
    contracts = publication_repository.get_contracts_for_publication(publication)
    return _determine_payment_status(
        publication,
        payment_repository.find_payment(publication),
        contracts,
    )


def get_payment_statuses(
    publication_ids: list[PublicationId],
) -> dict[PublicationId, PublicationPaymentStatus]:
    """Bulk fetch payment statuses.

    Replicates the logic of get_payment_status() but in bulk.

    Args:
        publication_ids: List of publication IDs to fetch statuses for

    Returns:
        Dict mapping publication ID to its payment status
    """
    contracts_by_pub = publication_repository.get_contracts_for_publications(publication_ids)
    payments_by_pub = payment_repository.find_payments(publication_ids)
    return {
        pub_id: _determine_payment_status(
            pub_id, payments_by_pub.get(pub_id), contracts_by_pub.get(pub_id, [])
        )
        for pub_id in publication_ids
    }


def update_payment(publication_id: PublicationId, payment_event: PaymentEvent) -> None:
    payment_repository.save_payment(publication_id, payment_event)


def bulk_update_payments(payment_updates: list[tuple[PublicationId, PaymentEvent]]) -> None:
    """
    Bulk update publication payment statuses for better performance.

    Args:
        payment_updates: List of (publication_id, payment_status) tuples
    """
    payment_repository.bulk_save_payments(payment_updates)


def invoice_deleted(publication_id: PublicationId, invoice_id: InvoiceId) -> None:
    payment_repository.delete_payment(publication_id, invoice_id)


def _consolidated_billing_contract(contracts: Iterable[ContractYear]) -> ContractYear | None:
    return next(
        (contract_year for contract_year in contracts if contract_year.uses_consolidated_billing()),
        None,
    )
