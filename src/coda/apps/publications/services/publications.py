from typing import cast

from coda.apps.publications.repositories import payment_repository, publication_repository
from coda.contract import ContractId, ContractYear
from coda.publication import BasePublication, PublicationId
from coda.publication.payment import (
    PublicationCoveredByContract,
    PublicationPayment,
    PublicationPaymentStatus,
    PublicationUnpaid,
)


def get_payment_status(id: PublicationId) -> PublicationPaymentStatus:
    publication = publication_repository.get_by_id(id)
    consolidated_billing = _consolidated_billing_contract(publication)
    if consolidated_billing:
        return PublicationCoveredByContract(
            contract_id=cast(ContractId, consolidated_billing.contract.id),
            contract_name=consolidated_billing.name,
            contract_year=consolidated_billing.year,
        )

    payment = payment_repository.find_payment(id)
    if payment:
        return payment

    return PublicationUnpaid()


def update_payment(publication_id: PublicationId, publication_payment: PublicationPayment) -> None:
    payment_repository.save_payment(publication_id, publication_payment)


def invoice_deleted(publication_id: PublicationId) -> None:
    payment_repository.delete_payment(publication_id)


def _consolidated_billing_contract(publication: BasePublication) -> ContractYear | None:
    return next(
        (
            contract_year
            for contract_year in publication.contracts
            if contract_year.uses_consolidated_billing()
        ),
        None,
    )
