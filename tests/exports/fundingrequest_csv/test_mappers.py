import pytest
import datetime

from coda.apps.exports.services.fundingrequest_csv.mappers import (
    map_funding_request_to_dto,
    map_funding_request_to_export_dto,
)
from coda.apps.invoices import funding_source_repository
from coda.contexts.finance.services import invoice_service
from coda.domain.finance.invoice import CreditorId
from coda.domain.money import Currency
from coda.domain.publication.publication import PublicationId

from tests import domainfactory, modelfactory

from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import ExternalFunding
from coda.apps.publications.models import (
    Concept,
    LinkType,
    Link,
    AttachedContract,
    PublicationAttachedConcept,
    Vocabulary,
)

from coda.domain.author import InstitutionId, Role
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequest, FundingOrganizationId
from coda.domain.publication import Monograph, License
from coda.domain.publication.publication import Authors
from coda.domain.string import NonEmptyStr


@pytest.mark.django_db
def test__funding_request_for_article__maps_to_dto__all_required_fields_are_mapped_correctly() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Test Publication")

    dto = map_funding_request_to_dto(funding_request)

    # Basic funding request fields
    assert dto.request_date == funding_request.request_date
    assert dto.legacy_request_id == funding_request.legacy_request_id

    # Publication fields
    assert dto.publication.title == "Test Publication"
    # Compare enum names (DTO has enum, model has string name)
    assert dto.publication.open_access_type.name == funding_request.publication.open_access_type
    assert dto.publication.kind == "article"
    assert funding_request.publication.article_journal is not None
    assert dto.publication.eissn == funding_request.publication.article_journal.eissn
    assert dto.publication.journal_name == funding_request.publication.article_journal.title
    assert (
        dto.publication.publisher_name == funding_request.publication.article_journal.publisher.name
    )


@pytest.mark.django_db
def test__funding_request_for_monograph__maps_to_dto__all_required_fields_are_mapped_correctly() -> (
    None
):
    publisher = modelfactory.publisher(name="Test Publisher")
    funding_org = modelfactory.funding_organization()
    monograph = Monograph.new(
        title=NonEmptyStr("Test Monograph"), publisher=PublisherId(publisher.pk)
    )

    request_id = repository.create(
        FundingRequest.new(
            monograph,
            domainfactory.payment(),
            external_funding=[
                domainfactory.external_funding(FundingOrganizationId(funding_org.pk))
            ],
            extra_contact=domainfactory.fundingrequest_contact(),
        )
    )
    monograph_funding_request = FundingRequestModel.objects.get(pk=request_id)

    dto = map_funding_request_to_dto(monograph_funding_request)

    assert dto.publication.title == "Test Monograph"
    assert dto.publication.kind == "monograph"
    assert dto.publication.eissn == ""
    assert dto.publication.journal_name == "Imported nameless journal"
    assert dto.publication.publisher_name == "Test Publisher"


@pytest.mark.django_db
def test__funding_request_with_one_external_funding__maps_to_dto__all_external_funding_fields_are_mapped_correctly() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Test Publication")

    dto = map_funding_request_to_dto(funding_request)

    assert len(dto.research_funding) > 0
    funding = dto.research_funding[0]
    assert funding.project_id is not None
    assert funding.funder is not None


@pytest.mark.django_db
def test__funding_request_with_multiple_external_fundings__maps_to_dto__all_external_funding_fields_are_mapped_correctly() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Test Publication")
    org1 = modelfactory.funding_organization(name="DFG")
    org2 = modelfactory.funding_organization(name="BMBF")

    # Add more external fundings to the existing one
    ExternalFunding.objects.create(
        funding_request=funding_request,
        organization=org1,
        project_id="DFG-123",
        project_name="DFG Project",
    )
    ExternalFunding.objects.create(
        funding_request=funding_request,
        organization=org2,
        project_id="BMBF-456",
        project_name="BMBF Project",
    )

    dto = map_funding_request_to_dto(funding_request)

    assert len(dto.research_funding) >= 2
    funders = {rf.funder for rf in dto.research_funding}
    project_ids = {rf.project_id for rf in dto.research_funding}
    assert "DFG" in funders
    assert "BMBF" in funders
    assert "DFG-123" in project_ids
    assert "BMBF-456" in project_ids


@pytest.mark.django_db
def test__funding_request_with_one_author__maps_to_dto__author_info_is_mapped_correctly() -> None:
    matching_author = domainfactory.author()
    funding_request = modelfactory.fundingrequest(
        title="Test Publication", authors=Authors([matching_author])
    )

    dto = map_funding_request_to_dto(funding_request)

    assert len(dto.publication.authors) == 1
    assert dto.publication.authors[0].name == matching_author.name
    assert dto.publication.authors[0].email == matching_author.email
    assert dto.publication.authors[0].orcid == matching_author.orcid
    assert dto.publication.authors[0].role == matching_author.role


@pytest.mark.django_db
def test__funding_request_with_multiple_authors__maps_to_dto__author_info_is_mapped_correctly() -> (
    None
):
    author1 = domainfactory.author(role=Role.CORRESPONDING_AUTHOR)
    author2 = domainfactory.author(role=Role.CO_AUTHOR)
    funding_request = modelfactory.fundingrequest(
        title="Test Publication", authors=Authors([author1, author2])
    )

    dto = map_funding_request_to_dto(funding_request)

    assert len(dto.publication.authors) == 2
    assert dto.publication.authors[0].name == author1.name
    assert dto.publication.authors[0].email == author1.email
    assert dto.publication.authors[1].name == author2.name
    assert dto.publication.authors[1].email == author2.email


@pytest.mark.django_db
def test__funding_request_with_one_author_with_affiliation__maps_to_dto__author_info_is_mapped_correctly() -> (
    None
):
    institution = modelfactory.institution()
    institution.name = "Test University"
    institution.save()
    author = domainfactory.author(affiliation=InstitutionId(institution.id))
    funding_request = modelfactory.fundingrequest(
        title="Test Publication", authors=Authors([author])
    )

    dto = map_funding_request_to_dto(funding_request)

    assert len(dto.publication.authors) == 1
    assert dto.publication.authors[0].affiliation == "Test University"


@pytest.mark.django_db
def test__funding_request_with_links__maps_to_dto__links_are_mapped_correctly() -> None:
    funding_request = modelfactory.fundingrequest(title="Test Publication")

    doi_type, _ = LinkType.objects.get_or_create(name="DOI")
    handle_type, _ = LinkType.objects.get_or_create(name="Handle")

    Link.objects.create(
        publication=funding_request.publication, type=doi_type, value="10.1234/test.doi"
    )
    Link.objects.create(
        publication=funding_request.publication, type=handle_type, value="hdl:1234/5678"
    )

    dto = map_funding_request_to_dto(funding_request)

    assert len(dto.publication.links) >= 2
    link_types = {link.type for link in dto.publication.links}
    link_values = {link.value for link in dto.publication.links}
    assert "DOI" in link_types
    assert "Handle" in link_types
    assert "10.1234/test.doi" in link_values
    assert "hdl:1234/5678" in link_values


@pytest.mark.django_db
def test__funding_request_with_contract__maps_to_dto__contract_info_is_mapped_correctly() -> None:
    funding_request = modelfactory.fundingrequest(title="Test Publication")
    contract = modelfactory.contract()
    contract.name = "DEAL Wiley"
    contract.save()

    AttachedContract.objects.create(
        publication=funding_request.publication, contract=contract, contract_year=2024
    )

    dto = map_funding_request_to_dto(funding_request)

    assert len(dto.publication.contracts) == 1
    assert dto.publication.contracts[0].name == "DEAL Wiley"
    assert dto.publication.contracts[0].year == 2024


@pytest.mark.django_db
def test__funding_request_with_subject_area_and_publication_type__maps_to_dto__all_fields_are_mapped_correctly() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Test Publication")

    vocab = Vocabulary.objects.create(name="Test Vocabulary")
    subject_area = PublicationAttachedConcept.objects.create(
        name="Computer Science", vocabulary=vocab
    )
    publication_type = PublicationAttachedConcept.objects.create(
        name="Research Article", vocabulary=vocab
    )

    funding_request.publication.subject_area = subject_area
    funding_request.publication.publication_type = publication_type
    funding_request.publication.save()

    dto = map_funding_request_to_dto(funding_request)

    assert dto.publication.subject_area.name == "Computer Science"
    assert dto.publication.publication_type.name == "Research Article"


@pytest.mark.django_db
def test__funding_request_with_concepts_from_vocabulary__maps_to_dto__concept_ids_are_mapped() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Concept Publication")

    vocab = Vocabulary.objects.create(name="Test Vocabulary")
    subject_area_concept = Concept.objects.create(
        vocabulary=vocab, concept_id="SA-001", name="Computer Science", hint=""
    )
    publication_type_concept = Concept.objects.create(
        vocabulary=vocab, concept_id="PT-002", name="Research Article", hint=""
    )
    funding_request.publication.subject_area = PublicationAttachedConcept.objects.create(
        name="Computer Science", vocabulary=vocab, entity_id=subject_area_concept.entity_id
    )
    funding_request.publication.publication_type = PublicationAttachedConcept.objects.create(
        name="Research Article", vocabulary=vocab, entity_id=publication_type_concept.entity_id
    )
    funding_request.publication.save()

    concept_ids = {
        subject_area_concept.entity_id: subject_area_concept.concept_id,
        publication_type_concept.entity_id: publication_type_concept.concept_id,
    }
    dto = map_funding_request_to_dto(funding_request, concept_ids=concept_ids)

    assert dto.publication.subject_area.concept_id == "SA-001"
    assert dto.publication.publication_type.concept_id == "PT-002"


@pytest.mark.django_db
def test__funding_request_without_concept_lookup__maps_to_dto__concept_ids_are_empty() -> None:
    funding_request = modelfactory.fundingrequest(title="Conceptless Publication")

    dto = map_funding_request_to_dto(funding_request)

    assert dto.publication.subject_area.concept_id == ""
    assert dto.publication.publication_type.concept_id == ""


@pytest.mark.django_db
def test__funding_request_with_license_and_publishing_state__maps_to_dto__all_fields_are_mapped_correctly() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Test Publication")
    funding_request.publication.license = License.CC_BY.name
    funding_request.publication.publication_state = "Published"
    funding_request.publication.online_publication_date = datetime.date(2024, 6, 15)
    funding_request.publication.print_publication_date = datetime.date(2024, 7, 1)
    funding_request.publication.save()

    dto = map_funding_request_to_dto(funding_request)

    assert dto.publication.license == License.CC_BY
    assert dto.publication.publishing_state.state == "published"
    assert dto.publication.publishing_state.online_date == datetime.date(2024, 6, 15)
    assert dto.publication.publishing_state.print_date == datetime.date(2024, 7, 1)


@pytest.mark.django_db
def test__funding_source_display_names__mapped_to_export_dto__institution_and_budget_names_are_used() -> (
    None
):
    funding_request = modelfactory.fundingrequest(title="Funding Source Display Publication")

    institution = modelfactory.institution()
    institution.name = "Test University"
    institution.save()
    institution_source = domainfactory.split_source(
        InstitutionId(institution.pk), "Test University"
    )
    budget_source = domainfactory.budget()
    institution_source.id = funding_source_repository.create(institution_source)
    budget_source.id = funding_source_repository.create(budget_source)

    budget_position = domainfactory.publication_position(
        PublicationId(funding_request.publication.id), currency=Currency.EUR
    )
    budget_position.assign_funding(budget_source, budget_position.cost.amount)

    institution_position = domainfactory.publication_position(
        PublicationId(funding_request.publication.id), currency=Currency.EUR
    )
    institution_position.assign_funding(institution_source, institution_position.cost.amount)

    unfunded_position = domainfactory.publication_position(
        PublicationId(funding_request.publication.id), currency=Currency.EUR
    )
    unfunded_position.assign_funding(None, unfunded_position.cost.amount)

    invoice = domainfactory.invoice(
        creditor=CreditorId(modelfactory.creditor().pk),
        positions=[budget_position, institution_position, unfunded_position],
    )
    invoice.id = invoice_service.save(invoice)

    dto = map_funding_request_to_export_dto(funding_request)

    names = [
        assignment.name
        for invoice_dto in dto.invoices
        for position in invoice_dto.positions
        for assignment in position.funding_assignments
    ]

    assert sorted(names) == sorted([budget_source.name, institution.name, ""])
