import datetime
from typing import cast

from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.institutions import repository as institution_repository
from coda.apps.journals import services as journal_services
from coda.apps.journals.models import Journal
from coda.apps.publications.repositories import vocabulary_repository
from coda.apps.publishers.models import Publisher
from coda.domain import orcid
from coda.domain.author import Author, InstitutionId, Role
from coda.domain.contract import ContractYear, PublisherId
from coda.domain.fundingrequest import (
    FundingRequestId,
    PublicFundingRequestId,
    Review,
    ReviewResult,
)
from coda.domain.fundingrequest.fundingrequest import (
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    Payment,
    PaymentMethod,
    TPublication,
)
from coda.domain.money import Currency, Money
from coda.domain.publication import (
    Authors,
    Doi,
    JournalId,
    License,
    Monograph,
    OpenAccessType,
    Publication,
    Published,
)
from coda.domain.string import NonEmptyStr
from coda.domain.vocabulary import VocabularyConcept, VocabularyProtocol
from tests.fundingrequests.fundingrequest_import.entitynames import (
    COAR_RESOURCE_TYPES_NAME,
    DFG_SUBJECT_CLASSIFICATION_NAME,
    IMPORT_CONTRACT_NAME,
    IMPORT_JOURNAL_ISSN,
    IMPORT_PUBLICATION_TITLE,
    IMPORT_PUBLISHER_NAME,
    IMPORT_RESEARCH_FUNDER_NAME,
)


def expected_review(id: FundingRequestId | None = None) -> Review:
    return Review(
        fundingrequest=id,
        result=ReviewResult.Approved,
        decided_funding=Money("1000.00", Currency.EUR),
        remarks="Remarks from the reviewer",
    )


def expected_article_request() -> FundingRequest[Publication]:
    return expected_request(for_=expected_article())


def expected_monograph_request() -> FundingRequest[Monograph]:
    return expected_request(for_=expected_monograph())


def expected_request(*, for_: TPublication) -> FundingRequest[TPublication]:
    funding_organization = FundingOrganization.objects.filter(
        name=IMPORT_RESEARCH_FUNDER_NAME
    ).first()
    assert funding_organization is not None, "Expected funding organization not found"
    funding_org_id = FundingOrganizationId(funding_organization.id)

    request_id = PublicFundingRequestId.create(date=datetime.date(2025, 3, 19))
    expected = FundingRequest(
        id=None,
        request_id=request_id,
        legacy_request_id="the-legacy-id",
        publication=for_,
        estimated_cost=Payment(amount=Money("1000.00", Currency.EUR), method=PaymentMethod.Unknown),
        request_remarks="Request remarks from the author",
        review=expected_review(),
        external_funding=[
            ExternalFunding(
                organization=funding_org_id,
                project_id=NonEmptyStr("123456"),
                project_name="My research project",
            )
        ],
        extra_contact=FilledContact(
            name=NonEmptyStr("Mr. Secretary"), email="secretary@example.com"
        ),
    )

    return expected


def expected_article() -> Publication:
    journal = cast(Journal, journal_services.find_by_eissn(IMPORT_JOURNAL_ISSN))
    publication = Publication.new(
        title=IMPORT_PUBLICATION_TITLE,
        journal=JournalId(journal.id),
        license=License.CC_BY,
        open_access_type=OpenAccessType.Gold,
        publication_state=Published(online=datetime.date(2025, 3, 19)),
        relevant_authors=expected_authors(),
        links={Doi("10.1234/5678")},
        subject_area=expected_subject_area(),
        publication_type=expected_publication_type(),
    )
    publication.contracts = expected_contracts()
    return publication


def expected_monograph() -> Monograph:
    publisher = Publisher.objects.filter(name=IMPORT_PUBLISHER_NAME).first()
    assert publisher is not None, "Expected publisher not found"
    monograph = Monograph.new(
        title=NonEmptyStr("My article"),
        publisher=PublisherId(publisher.id),
        license=License.CC_BY,
        open_access_type=OpenAccessType.Gold,
        publication_state=Published(online=datetime.date(2025, 3, 19)),
        relevant_authors=expected_authors(),
        links={Doi("10.1234/5678")},
        subject_area=expected_subject_area(),
        publication_type=expected_publication_type(),
    )
    monograph.contracts = expected_contracts()
    return monograph


def expected_publication_type() -> VocabularyConcept:
    try:
        coar_resource_types = vocabulary_repository.newest_base_vocabulary_by_name(
            COAR_RESOURCE_TYPES_NAME
        )
    except vocabulary_repository.EntityNotFoundError:
        raise AssertionError("COAR resource types vocabulary not found")

    return find_concept_by_name(coar_resource_types, "journal article")


def expected_subject_area() -> VocabularyConcept:
    try:
        dfg_classification = vocabulary_repository.newest_base_vocabulary_by_name(
            DFG_SUBJECT_CLASSIFICATION_NAME
        )
    except vocabulary_repository.EntityNotFoundError:
        raise AssertionError("DFG subject classification not found")

    return find_concept_by_name(dfg_classification, "Humanities")


def find_concept_by_name(v: VocabularyProtocol, concept_name: str) -> VocabularyConcept:
    return [c for c in v.concepts if c.name == concept_name][0]


def expected_authors() -> Authors:
    matches = institution_repository.search("University of Example")
    try:
        first_match = next(iter(matches))
    except StopIteration:
        raise AssertionError("Expected institution not found")

    return Authors(
        [
            Author.new(
                name=NonEmptyStr("Alice Doe"),
                email="a.doe@example.com",
                orcid=orcid.Orcid("0000-0002-1825-0097"),
                role=Role.CORRESPONDING_AUTHOR,
                affiliation=InstitutionId(first_match.id),
            )
        ]
    )


def expected_contracts() -> tuple[ContractYear, ...]:
    contract = contract_repository.get_by_name(IMPORT_CONTRACT_NAME)
    assert contract is not None
    contract_year = contract.in_year(2025)
    return (contract_year,)
