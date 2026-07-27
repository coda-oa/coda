import pytest

from coda.apps.exports.services.contract_csv.dtos import ContractLinkDto
from coda.apps.exports.services.contract_csv.mappers import (
    map_contract_to_dto,
    map_contract_to_export_dto,
)
from coda.contexts.finance.dto.import_dtos import ContractPositionImportDto
from coda.domain.contract import PublisherId
from coda.domain.publication.publication import JournalId
from tests import domainfactory, modelfactory
from coda.apps.contracts import repository as contract_repository
from coda.apps.contracts.models import Contract as ContractModel, ContractLink, ContractLinkType
from coda.apps.invoices.models import Invoice as InvoiceModel
from tests.exports.helpers import create_invoice_with_contract_position


@pytest.mark.django_db
def test__contract_without_invoices__maps_to_dto__all_required_fields_are_mapped_correctly() -> (
    None
):
    contract = domainfactory.contract()

    publisher = modelfactory.publisher(name="Test Publisher")
    journal = modelfactory.journal(title="Test Journal")
    contract.publishers = [PublisherId(publisher.id)]
    contract.journals = [JournalId(journal.id)]

    contract.id = contract_repository.create(contract)
    contract_model = ContractModel.objects.get(pk=int(contract.id))

    contract_dto = map_contract_to_dto(contract_model)

    assert contract_dto.name == contract.name
    assert contract_dto.start_date == contract.period.start
    assert contract_dto.end_date == contract.period.end
    assert contract_dto.publishers == ["Test Publisher"]
    assert contract_dto.journals == ["Test Journal"]
    assert contract_dto.publication_billing == contract.publication_billing
    assert contract_dto.active == contract.is_active()


@pytest.mark.django_db
def test__contract_with_esac__maps_to_dto__all_required_fields_are_mapped_correctly() -> None:
    contract = domainfactory.contract()
    contract.id = contract_repository.create(contract)

    contract_model = ContractModel.objects.get(pk=int(contract.id))
    esac_type, _ = ContractLinkType.objects.get_or_create(name="ESAC")
    esac_link = ContractLink.objects.create(
        contract=contract_model,
        type=esac_type,
        value="esac-12345",
    )

    contract_dto = map_contract_to_dto(contract_model)

    assert contract_dto.links == [ContractLinkDto(type=esac_link.type.name, value=esac_link.value)]


@pytest.mark.django_db
def test__contract_with_oai__maps_to_dto__all_required_fields_are_mapped_correctly() -> None:
    contract = domainfactory.contract()
    contract.id = contract_repository.create(contract)

    contract_model = ContractModel.objects.get(pk=int(contract.id))
    oai_type, _ = ContractLinkType.objects.get_or_create(name="OAI")
    oai_link = ContractLink.objects.create(
        contract=contract_model,
        type=oai_type,
        value="oai:digitalcommons.odu.edu:oaweek-1012",
    )

    contract_dto = map_contract_to_dto(contract_model)

    assert contract_dto.links == [ContractLinkDto(type=oai_link.type.name, value=oai_link.value)]


@pytest.mark.django_db
def test__contract_with_ezb__maps_to_dto__all_required_fields_are_mapped_correctly() -> None:
    contract = domainfactory.contract()
    contract.id = contract_repository.create(contract)

    contract_model = ContractModel.objects.get(pk=int(contract.id))
    ezb_type, _ = ContractLinkType.objects.get_or_create(name="EZB")
    ezb_link = ContractLink.objects.create(
        contract=contract_model,
        type=ezb_type,
        value="ezb-12345",
    )

    contract_dto = map_contract_to_dto(contract_model)

    assert contract_dto.links == [ContractLinkDto(type=ezb_link.type.name, value=ezb_link.value)]


@pytest.mark.django_db
def test__contract_with_multiple_links__maps_to_dto__all_required_fields_are_mapped_correctly() -> (
    None
):
    contract = domainfactory.contract()
    contract.id = contract_repository.create(contract)

    contract_model = ContractModel.objects.get(pk=int(contract.id))
    esac_type, _ = ContractLinkType.objects.get_or_create(name="ESAC")
    oai_type, _ = ContractLinkType.objects.get_or_create(name="OAI")
    ezb_type, _ = ContractLinkType.objects.get_or_create(name="EZB")

    esac_link = ContractLink.objects.create(
        contract=contract_model,
        type=esac_type,
        value="esac-12345",
    )
    oai_link = ContractLink.objects.create(
        contract=contract_model,
        type=oai_type,
        value="oai:digitalcommons.odu.edu:oaweek-1012",
    )
    ezb_link = ContractLink.objects.create(
        contract=contract_model,
        type=ezb_type,
        value="ezb-12345",
    )

    contract_dto = map_contract_to_dto(contract_model)

    expected_links = [
        ContractLinkDto(type=esac_link.type.name, value=esac_link.value),
        ContractLinkDto(type=oai_link.type.name, value=oai_link.value),
        ContractLinkDto(type=ezb_link.type.name, value=ezb_link.value),
    ]

    assert sorted(contract_dto.links, key=lambda x: x.type) == sorted(
        expected_links, key=lambda x: x.type
    )


@pytest.mark.django_db
def test__contract_and_invoice__mapped_to_composite_export_dto__all_required_fields_are_mapped_correctly() -> (
    None
):
    contract = domainfactory.contract()
    contract.id = contract_repository.create(contract)
    contract_year = domainfactory.contract_year(contract)
    contract_model = ContractModel.objects.get(pk=int(contract.id))

    invoice = create_invoice_with_contract_position(contract_year)
    assert invoice.id is not None
    invoice_model = InvoiceModel.objects.get(pk=int(invoice.id))

    dto = map_contract_to_export_dto(contract_model)

    invoice_position = next(iter(invoice.positions))

    assert dto.contract.name == contract.name
    assert dto.contract.start_date == contract.period.start
    assert dto.contract.end_date == contract.period.end
    assert dto.contract.publishers == [
        publisher.name for publisher in contract_model.publishers.all()
    ]
    assert dto.contract.journals == [journal.title for journal in contract_model.journals.all()]
    assert dto.contract.publication_billing == contract_model.publication_billing
    assert dto.contract.active == contract_model.active_status

    assert len(dto.invoices) == 1
    assert dto.invoices[0].number == invoice.number
    assert dto.invoices[0].date == invoice.date
    assert dto.invoices[0].creditor == invoice_model.creditor.name
    assert dto.invoices[0].status == invoice.status
    assert dto.invoices[0].comment == invoice.comment
    assert dto.invoices[0].external_id == invoice.external_invoice_id

    assert dto.invoices[0].positions[0].amount == invoice_position.cost.amount
    assert dto.invoices[0].positions[0].tax_rate == invoice_position.tax_rate * 100
    assert dto.invoices[0].positions[0].cost_type.value == invoice_position.item.cost_type.value
    assert dto.invoices[0].positions[0].external_id == invoice_position.external_position_id
    assert isinstance(dto.invoices[0].positions[0], ContractPositionImportDto)
    assert dto.invoices[0].positions[0].contract_year == contract_year.year
    assert dto.invoices[0].positions[0].contract_name == contract.name
