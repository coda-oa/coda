import datetime
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import date
from io import StringIO
from pathlib import Path

import pytest

from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.fundingrequests.models import FundingOrganization, Label
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.institutions import repository as institution_repository
from coda.apps.institutions.models import Institution
from coda.apps.journals import services as journal_services
from coda.apps.publishers.models import Publisher
from coda.contexts.fundingrequest.dto.import_dtos import (
    ContractImportDto,
    FundingRequestImportDto,
    FundingRequestImportListDto,
    PublicationImportDto,
)
from coda.contexts.fundingrequest.services import labels as label_services
from coda.contexts.fundingrequest.services.checks import get_checkrun
from coda.contexts.fundingrequest.services.import_service import import_fundingrequests
from coda.domain.author import InstitutionId
from coda.domain.color import Color
from coda.domain.contract import Contract, PublisherId
from coda.domain.date import DateRange
from coda.domain.fundingrequest import Review
from coda.domain.fundingrequest.fundingrequest import AnyFundingRequest, FundingOrganizationId
from coda.domain.publication.publication import OpenAccessType, Publication
from coda.domain.string import NonEmptyStr
from tests import modelfactory
from tests.fundingrequests.fundingrequest_import import fullrequest, minimalrequest
from tests.fundingrequests.fundingrequest_import.entitynames import (
    IMPORT_AUTHOR_AFFILIATION,
    IMPORT_CONTRACT_NAME,
    IMPORT_JOURNAL_ISSN,
    IMPORT_JOURNAL_NAME,
    IMPORT_LABEL_NAME,
    IMPORT_PUBLISHER_NAME,
    IMPORT_RESEARCH_FUNDER_NAME,
)
from tests.fundingrequests.services.test_fundingrequest_services import assert_fundingrequest_eq

CWD = Path(__file__).parent
JSON_PATH = CWD / "fundingrequest_import.json"


@pytest.fixture(autouse=True)
def remove_json() -> Generator[None]:
    yield
    JSON_PATH.unlink(missing_ok=True)


def write_json(importdata: FundingRequestImportListDto) -> None:
    with JSON_PATH.open("w") as json_file:
        json_file.write(importdata.model_dump_json())


@dataclass
class RequestVariant:
    importdata: FundingRequestImportListDto
    expected_request: Callable[[], AnyFundingRequest]
    expected_review: Callable[[], Review]


RequestVariants = [
    RequestVariant(
        importdata=fullrequest.full_article_request_import(),
        expected_request=fullrequest.expected_article_request,
        expected_review=fullrequest.expected_review,
    ),
    RequestVariant(
        importdata=fullrequest.full_monograph_request_import(),
        expected_request=fullrequest.expected_monograph_request,
        expected_review=fullrequest.expected_review,
    ),
    RequestVariant(
        importdata=minimalrequest.minimal_article_request_import(),
        expected_request=minimalrequest.expected_article_request,
        expected_review=minimalrequest.expected_review,
    ),
    RequestVariant(
        importdata=minimalrequest.minimal_monograph_request_import(),
        expected_request=minimalrequest.expected_monograph_request,
        expected_review=minimalrequest.expected_review,
    ),
]


@pytest.mark.django_db
@pytest.mark.parametrize("request_variant", RequestVariants)
def test__import_fundingrequest__saves_fundingrequest_and_creates_missing_entities(
    request_variant: RequestVariant,
) -> None:
    write_json(request_variant.importdata)

    with JSON_PATH.open() as json_file:
        report = import_fundingrequests(json_file)

    print(repr(report))
    fundingrequest = fundingrequest_repository.first()

    assert fundingrequest is not None
    id = fundingrequest.id
    review = fundingrequest_repository.get_review(id)

    request_model = FundingRequestModel.objects.get(id=id.pk)
    expected_label_names = set(request_variant.importdata.requests[0].labels)
    actual_label_names = set(request_model.labels.values_list("name", flat=True))

    assert_fundingrequest_eq(fundingrequest, request_variant.expected_request())
    assert_review_eq(review, request_variant.expected_review())
    assert actual_label_names == expected_label_names


@pytest.mark.django_db
def test__import_multiple_requests_with_same_contract_in_different_years__contract_period_spans_imported_years() -> (
    None
):
    first_year, second_year = 1990, 2026
    import_dto = FundingRequestImportListDto(
        requests=[
            FundingRequestImportDto(
                request_date=datetime.date.today(),
                publication=PublicationImportDto(
                    kind="monograph",
                    title="pub 1",
                    publisher_name="publisher 1",
                    open_access_type=OpenAccessType.Gold,
                    contracts=[ContractImportDto(name="my-contract", year=second_year)],
                ),
            ),
            FundingRequestImportDto(
                request_date=datetime.date.today(),
                publication=PublicationImportDto(
                    kind="monograph",
                    title="pub 2",
                    publisher_name="publisher 1",
                    open_access_type=OpenAccessType.Gold,
                    contracts=[ContractImportDto(name="my-contract", year=first_year)],
                ),
            ),
        ]
    )

    json = StringIO(import_dto.model_dump_json())
    _ = import_fundingrequests(json)

    actual = contract_repository.get_by_name("my-contract")
    assert actual is not None
    assert actual.period == DateRange(datetime.date(1990, 1, 1), datetime.date(2026, 12, 31))


@pytest.mark.django_db
@pytest.mark.parametrize("request_variant", RequestVariants)
def test__import_fundingrequest__does_not_run_checks(request_variant: RequestVariant) -> None:
    write_json(request_variant.importdata)

    with JSON_PATH.open() as json_file:
        import_fundingrequests(json_file)

    fundingrequest = fundingrequest_repository.first()
    assert fundingrequest is not None

    id = fundingrequest.id
    checkrun = get_checkrun(id)
    assert checkrun is None


def assert_review_eq(actual: Review, expected: Review) -> None:
    assert actual.result == expected.result
    assert actual.decided_funding == expected.decided_funding
    assert actual.remarks == expected.remarks


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
def test__import_monograph_fundingrequest__does_not_create_journal() -> None:
    requests = fullrequest.full_monograph_request_import()
    write_json(requests)

    with JSON_PATH.open() as json_file:
        import_fundingrequests(json_file)

    assert_no_journal_created_on_import()
    assert_new_publisher_exists()


def assert_new_publisher_exists() -> None:
    assert Publisher.objects.filter(name=IMPORT_PUBLISHER_NAME).exists()


@pytest.mark.django_db
def test__given_invalid_publication_title__import__returns_errors() -> None:
    requests = fullrequest.full_article_request_import()
    request = requests.requests[0]
    request.publication.title = ""
    write_json(requests)

    with JSON_PATH.open() as json_file:
        report = import_fundingrequests(json_file)

    assert report.valid_requests == 0
    assert report.invalid_requests == 1
    assert request.legacy_request_id in report.errors


@pytest.mark.django_db
def test__given_invalid_contract_year__import__returns_errors() -> None:
    contract = Contract.new(
        NonEmptyStr(IMPORT_CONTRACT_NAME),
        period=DateRange.create(
            start=date(1900, 1, 1),
            end=date(1900, 12, 31),
        ),
    )
    contract.id = contract_repository.create(contract)

    requests = fullrequest.full_article_request_import()
    write_json(requests)

    with JSON_PATH.open() as json_file:
        report = import_fundingrequests(json_file)

    invalid_request = requests.requests[0]
    assert report.valid_requests == 0
    assert report.invalid_requests == 1
    assert invalid_request.legacy_request_id in report.errors


@pytest.mark.django_db
def test__given_invalid_and_valid_requests__import__saves_only_valid_requests() -> None:
    invalid_request = fullrequest.full_article_request_import().requests[0]
    invalid_request.publication.title = ""
    invalid_request.legacy_request_id = "invalid-legacy-id"

    valid_request = fullrequest.full_article_request_import().requests[0]

    all_requests = FundingRequestImportListDto(requests=[invalid_request, valid_request])
    imported_request = fundingrequest_repository.first()
    write_json(all_requests)

    with JSON_PATH.open() as json_file:
        report = import_fundingrequests(json_file)

    imported_request = fundingrequest_repository.first()
    assert len(fundingrequest_repository.all()) == 1
    assert_fundingrequest_eq(imported_request, fullrequest.expected_article_request())
    assert "invalid-legacy-id" in report.errors
    assert "valid-legacy-id" not in report.errors


@pytest.mark.django_db
def test__import_article_fundingrequests__saves_fundingrequests_without_creating_existing_entities() -> (
    None
):
    write_json(fullrequest.full_article_request_import())

    publisher = PublisherId(modelfactory.publisher().pk)
    journal_services.create(NonEmptyStr("Another title"), IMPORT_JOURNAL_ISSN, publisher)
    contract = Contract.new(name=NonEmptyStr(IMPORT_CONTRACT_NAME))
    contract_repository.create(contract)
    institution_repository.create(IMPORT_AUTHOR_AFFILIATION)
    modelfactory.funding_organization(IMPORT_RESEARCH_FUNDER_NAME)
    label_services.label_create(name=IMPORT_LABEL_NAME, color=Color.from_hex("#FF0000"))

    with JSON_PATH.open() as json_file:
        import_fundingrequests(json_file)

    assert_no_institution_created_on_import()
    assert_no_journal_created_on_import()
    assert_no_publisher_created_on_import()
    assert_no_contract_created_on_import()
    assert_no_research_funder_created_on_import()
    assert_no_label_created_on_import()

    fundingrequest = fundingrequest_repository.first()
    assert_fundingrequest_eq(fundingrequest, fullrequest.expected_article_request())


@pytest.mark.django_db
def test__given_existing_related_entities_with_multiple_duplicate_names__import__picks_first_match() -> (
    None
):
    write_json(fullrequest.full_article_request_import())
    publisher = modelfactory.publisher(name=IMPORT_PUBLISHER_NAME)
    _ = modelfactory.publisher(name=IMPORT_PUBLISHER_NAME)

    contract = Contract.new(name=NonEmptyStr(IMPORT_CONTRACT_NAME))
    contract.id = contract_repository.create(contract)

    _ = contract_repository.create(Contract.new(name=NonEmptyStr(IMPORT_CONTRACT_NAME)))

    institution = institution_repository.create(IMPORT_AUTHOR_AFFILIATION)
    _ = institution_repository.create(IMPORT_AUTHOR_AFFILIATION)

    funding_org = modelfactory.funding_organization(name=IMPORT_RESEARCH_FUNDER_NAME)
    _ = modelfactory.funding_organization(name=IMPORT_RESEARCH_FUNDER_NAME)

    label = label_services.label_create(name=IMPORT_LABEL_NAME, color=Color.from_hex("#00FF00"))
    _ = label_services.label_create(name=IMPORT_LABEL_NAME, color=Color.from_hex("#00FF00"))

    with JSON_PATH.open() as json_file:
        import_fundingrequests(json_file)

    request = fundingrequest_repository.first()
    assert request is not None
    assert isinstance(request.publication, Publication)

    journal = journal_services.get_by_pk(request.publication.journal)
    assert journal.publisher.id == publisher.pk

    funding, *_ = request.external_funding
    assert funding.organization == FundingOrganizationId(funding_org.pk)

    author, *_ = request.publication.relevant_authors
    assert author.affiliation == InstitutionId(institution.pk)

    request_model = FundingRequestModel.objects.get(id=request.id.pk)
    attached_label, *_ = request_model.labels.all()
    assert attached_label.pk == label.pk


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


def assert_no_institution_created_on_import() -> None:
    assert Institution.objects.filter(name=IMPORT_AUTHOR_AFFILIATION).count() == 1


def assert_no_label_created_on_import() -> None:
    assert Label.objects.filter(name=IMPORT_LABEL_NAME).count() == 1
