import pytest

from coda.domain.opencost import (
    ContractAmountsPaid,
    ContractCostDataType,
    ContractSecondaryIdentifiersType,
    Dates,
    PublicationCostDataType,
    PublicationPrimaryIdentifier,
    PublicationSecondaryIdentifiers,
)


def test__publication_secondary_identifier__needs_at_least_one_id() -> None:
    with pytest.raises(ValueError):
        _ = PublicationSecondaryIdentifiers(id=[])


def test__publication_primary_identifier__needs_doi_or_bibliographic_information() -> None:
    with pytest.raises(ValueError):
        _ = PublicationPrimaryIdentifier(doi=None, bibliographic_information=None)


def test__publication_cost_data_type__needs_either_invoice_or_contract() -> None:
    with pytest.raises(ValueError):
        _ = PublicationCostDataType(invoice=None, part_of_contract=None)

    with pytest.raises(ValueError):
        _ = PublicationCostDataType(invoice=[], part_of_contract=None)


def test__contract_secondary_identifier__needs_at_least_one_id() -> None:
    with pytest.raises(ValueError):
        _ = ContractSecondaryIdentifiersType(id=[])


def test__dates_requires_invoice_or_paid() -> None:
    with pytest.raises(ValueError):
        _ = Dates(invoice=None, paid=None)


def test__contract_amount_paid__requires_at_least_one_item() -> None:
    with pytest.raises(ValueError):
        _ = ContractAmountsPaid(amount_paid=[])


def test__contract_cost_data__requires_at_least_one_invoice_group() -> None:
    with pytest.raises(ValueError):
        _ = ContractCostDataType(invoice_group=[])
