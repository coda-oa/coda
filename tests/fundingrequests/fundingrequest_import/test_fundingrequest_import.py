from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from coda.apps.contracts import repository as contract_repository
from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.apps.fundingrequests.models import FundingOrganization
from coda.apps.fundingrequests.services.checks import get_checkrun
from coda.apps.fundingrequests.services.importservice import import_fundingrequests
from coda.apps.fundingrequests.services.importservice.dto import (
    FundingRequestImportListDto,
)
from coda.apps.institutions import repository as institution_repository
from coda.apps.institutions.models import Institution
from coda.apps.journals import services as journal_services
from coda.apps.publishers.models import Publisher
from coda.domain.contract import Contract, PublisherId
from coda.domain.fundingrequest import FundingRequestId, Review
from coda.domain.fundingrequest.fundingrequest import AnyFundingRequest
from coda.domain.string import NonEmptyStr
from tests import modelfactory
from tests.fundingrequests.fundingrequest_import import fullrequest, minimalrequest
from tests.fundingrequests.fundingrequest_import.entitynames import (
    IMPORT_AUTHOR_AFFILIATION,
    IMPORT_CONTRACT_NAME,
    IMPORT_JOURNAL_ISSN,
    IMPORT_JOURNAL_NAME,
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
        import_fundingrequests(json_file)

    fundingrequest = fundingrequest_repository.first()
    assert fundingrequest is not None
    id = cast(FundingRequestId, fundingrequest.id)
    review = fundingrequest_repository.get_review(id)
    assert_fundingrequest_eq(fundingrequest, request_variant.expected_request())
    assert_review_eq(review, request_variant.expected_review())


@pytest.mark.django_db
@pytest.mark.parametrize("request_variant", RequestVariants)
def test__import_fundingrequest__does_not_run_checks(request_variant: RequestVariant) -> None:
    write_json(request_variant.importdata)

    with JSON_PATH.open() as json_file:
        import_fundingrequests(json_file)

    fundingrequest = fundingrequest_repository.first()
    assert fundingrequest is not None

    id = cast(FundingRequestId, fundingrequest.id)
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
def test__import_article_fundingrequests__saves_fundingrequests_without_creating_existing_entities() -> (
    None
):
    write_json(fullrequest.full_article_request_import())

    publisher = PublisherId(modelfactory.publisher().id)
    journal_services.create(NonEmptyStr("Another title"), IMPORT_JOURNAL_ISSN, publisher)
    contract = Contract.new(name=NonEmptyStr(IMPORT_CONTRACT_NAME))
    contract_repository.create(contract)
    institution_repository.create(IMPORT_AUTHOR_AFFILIATION)
    modelfactory.funding_organization(IMPORT_RESEARCH_FUNDER_NAME)

    with JSON_PATH.open() as json_file:
        import_fundingrequests(json_file)

    assert_no_institution_created_on_import()
    assert_no_journal_created_on_import()
    assert_no_publisher_created_on_import()
    assert_no_contract_created_on_import()
    assert_no_research_funder_created_on_import()

    fundingrequest = fundingrequest_repository.first()
    assert_fundingrequest_eq(fundingrequest, fullrequest.expected_article_request())


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
