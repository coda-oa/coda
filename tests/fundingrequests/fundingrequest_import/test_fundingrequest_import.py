from collections.abc import Generator
import datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from coda import orcid
from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.fundingrequests.services.fundingrequest_import import (
    import_fundingrequests,
)
from coda.apps.fundingrequests.services.fundingrequest_import.dto import (
    AuthorImportDto,
    ConceptImportDto,
    ContractImportDto,
    CostEstimateImportDto,
    DecidedFundingImportDto,
    FundingRequestImportDto,
    FundingRequestImportListDto,
    LinkImportDto,
    PublicationImportDto,
    PublishingStateImportDto,
    ResearchFundingImportDto,
    ReviewImportDto,
    SeperateContactImportDto,
)
from coda.apps.journals import services as journal_services
from coda.apps.journals.models import Journal
from coda.apps.publications.repositories import vocabulary_repository
from coda.apps.publishers.models import Publisher
from coda.author import Author, Role
from coda.contract import Contract, PublisherId
from coda.fundingrequest import (
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    Payment,
    PaymentMethod,
    Review,
    ReviewResult,
)
from coda.fundingrequest.identity import PublicFundingRequestId
from coda.issn import Issn
from coda.money import Currency, Money
from coda.publication import (
    Authors,
    Doi,
    JournalId,
    License,
    OpenAccessType,
    Publication,
    Published,
)
from coda.string import NonEmptyStr
from coda.vocabulary import VocabularyConcept, VocabularyProtocol
from tests import modelfactory
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq

CWD = Path(__file__).parent
JSON_PATH = CWD / "fundingrequest_import.json"


@pytest.fixture(autouse=True, scope="module")
def write_json() -> Generator[None]:
    with JSON_PATH.open("w") as json_file:
        json_file.write(FUNDINGREQUEST_IMPORT.model_dump_json(indent=4))

    yield

    JSON_PATH.unlink()


@pytest.mark.django_db
def test__import_fundingrequest__saves_fundingrequest_and_creates_missing_entities() -> None:
    with JSON_PATH.open() as json_file:
        import_fundingrequests(json_file)

    assert_new_journal_exists()
    assert_new_contract_exists()
    assert_new_research_funder_exists()

    fundingrequest = fundingrequest_repository.first()
    assert_fundingrequest_eq(fundingrequest, expected_request())


def assert_new_journal_exists() -> None:
    journal = journal_services.find_by_eissn(IMPORT_JOURNAL_ISSN)
    assert journal is not None
    assert journal.title == "My journal"
    assert journal.publisher.name == "My publisher"


def assert_new_contract_exists() -> None:
    contract = contract_repository.get_by_name(IMPORT_CONTRACT_NAME)
    assert contract is not None


def assert_new_research_funder_exists() -> None:
    assert FundingOrganization.objects.filter(name=IMPORT_RESEARCH_FUNDER_NAME).exists()


@pytest.mark.django_db
def test__import_fundingrequests__saves_fundingrequests_without_creating_existing_entities() -> (
    None
):
    publisher = PublisherId(modelfactory.publisher().id)
    journal_services.create(NonEmptyStr("Another title"), IMPORT_JOURNAL_ISSN, publisher)
    contract = Contract.new(name=NonEmptyStr(IMPORT_CONTRACT_NAME))
    contract_repository.save(contract)
    modelfactory.funding_organization(IMPORT_RESEARCH_FUNDER_NAME)

    with JSON_PATH.open() as json_file:
        import_fundingrequests(json_file)

    assert_no_journal_created_on_import()
    assert_no_publisher_created_on_import()
    assert_no_contract_created_on_import()
    assert_no_research_funder_created_on_import()
    assert_fundingrequest_eq(fundingrequest_repository.first(), expected_request())


def assert_no_journal_created_on_import() -> None:
    journals = journal_services.find_by_title(IMPORT_JOURNAL_NAME)
    assert list(journals) == []


def assert_no_publisher_created_on_import() -> None:
    publishers = Publisher.objects.filter(name=IMPORT_PUBLISHER_NAME).all()
    assert list(publishers) == []


def assert_no_contract_created_on_import() -> None:
    contracts = contract_repository.all()
    assert len(contracts) == 1


def assert_no_research_funder_created_on_import() -> None:
    assert FundingOrganization.objects.filter(name=IMPORT_RESEARCH_FUNDER_NAME).count() == 1


DFG_SUBJECT_CLASSIFICATION_NAME = "DFG Subject Classification"
COAR_RESOURCE_TYPES_NAME = "COAR Resource Types"

IMPORT_CONTRACT_NAME = "My contract"
IMPORT_JOURNAL_NAME = "My journal"
IMPORT_JOURNAL_ISSN = Issn("2434-561X")
IMPORT_PUBLISHER_NAME = "My publisher"
IMPORT_RESEARCH_FUNDER_NAME = "New Research Funder"
FUNDINGREQUEST_IMPORT = FundingRequestImportListDto(
    requests=[
        FundingRequestImportDto(
            request_date=datetime.date(2025, 3, 19),
            review=ReviewImportDto(
                result=ReviewResult.Approved,
                funding=DecidedFundingImportDto(
                    amount=Decimal("1000.00"), currency=Currency.EUR.code
                ),
                remarks="Remarks from the reviewer",
            ),
            estimated_cost=CostEstimateImportDto(
                amount=Decimal("1000.00"),
                currency=Currency.EUR.code,
                payment_method=PaymentMethod.Unknown,
            ),
            research_funding=[
                ResearchFundingImportDto(
                    funder=IMPORT_RESEARCH_FUNDER_NAME,
                    project_id="123456",
                    project_name="My research project",
                )
            ],
            request_remarks="Request remarks from the author",
            seperate_contact=SeperateContactImportDto(
                name="Mr. Secretary", email="secretary@example.com"
            ),
            publication=PublicationImportDto(
                title="My article",
                kind="article",
                license=License.CC_BY,
                eissn=str(IMPORT_JOURNAL_ISSN),
                journal_name=IMPORT_JOURNAL_NAME,
                publisher_name=IMPORT_PUBLISHER_NAME,
                open_access_type=OpenAccessType.Gold,
                publishing_state=PublishingStateImportDto(
                    online_date=datetime.date(2025, 3, 19), state="published"
                ),
                authors=[
                    AuthorImportDto(
                        name="Alice Doe",
                        email="a.doe@example.com",
                        orcid="0000-0002-1825-0097",
                        role=Role.CORRESPONDING_AUTHOR,
                    )
                ],
                subject_area=ConceptImportDto(
                    vocabulary_name=DFG_SUBJECT_CLASSIFICATION_NAME, name="Humanities"
                ),
                publication_type=ConceptImportDto(
                    vocabulary_name=COAR_RESOURCE_TYPES_NAME, name="journal article"
                ),
                links=[LinkImportDto(type="DOI", value="10.1234/5678")],
                contracts=[ContractImportDto(name=IMPORT_CONTRACT_NAME, year=2025)],
            ),
        )
    ]
)


def expected_request() -> FundingRequest[Publication]:
    journal = cast(Journal, journal_services.find_by_eissn(IMPORT_JOURNAL_ISSN))
    dfg_classification = vocabulary_repository.newest_base_vocabulary_by_name(
        DFG_SUBJECT_CLASSIFICATION_NAME
    )
    coar_resource_types = vocabulary_repository.newest_base_vocabulary_by_name(
        COAR_RESOURCE_TYPES_NAME
    )

    expected_subject_area = find_concept_by_name(dfg_classification, "Humanities")
    expected_publication_type = find_concept_by_name(coar_resource_types, "journal article")
    expected_publication = Publication.new(
        title=NonEmptyStr("My article"),
        journal=JournalId(journal.id),
        license=License.CC_BY,
        open_access_type=OpenAccessType.Gold,
        publication_state=Published(online=datetime.date(2025, 3, 19)),
        relevant_authors=Authors(
            [
                Author.new(
                    name=NonEmptyStr("Alice Doe"),
                    email="a.doe@example.com",
                    orcid=orcid.Orcid("0000-0002-1825-0097"),
                    role=Role.CORRESPONDING_AUTHOR,
                )
            ]
        ),
        links={Doi("10.1234/5678")},
        subject_area=expected_subject_area,
        publication_type=expected_publication_type,
    )

    contract = contract_repository.get_by_name("My contract")
    assert contract is not None
    contract_year = contract.in_year(2025)
    expected_publication.contracts = (contract_year,)

    funding_organization = FundingOrganization.objects.get(name=IMPORT_RESEARCH_FUNDER_NAME)
    funding_org_id = FundingOrganizationId(funding_organization.id)

    request_id = PublicFundingRequestId.create(date=datetime.date(2025, 3, 19))
    expected = FundingRequest(
        id=None,
        request_id=request_id,
        publication=expected_publication,
        estimated_cost=Payment(
            amount=Money(Decimal("1000.00"), Currency.EUR), method=PaymentMethod.Unknown
        ),
        request_remarks="Request remarks from the author",
        review=Review(
            fundingrequest=None,
            result=ReviewResult.Approved,
            decided_funding=Money(Decimal("1000.00"), Currency.EUR),
            remarks="Remarks from the reviewer",
        ),
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


def find_concept_by_name(v: VocabularyProtocol, concept_name: str) -> VocabularyConcept:
    return [c for c in v.concepts if c.name == concept_name][0]
