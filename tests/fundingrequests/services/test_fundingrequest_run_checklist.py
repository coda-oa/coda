from collections.abc import Callable
from typing import Any, cast

import pytest

from coda.apps.contracts import repository as contract_repository
from coda.contexts.fundingrequest.services import checks, fundingrequests
from coda.contexts.fundingrequest.dto.commands import UpdatePublicationMetadataCommand
from coda.apps.publications.dto import ContractYearDto, PublicationDto
from coda.checks.checkfactory import CheckFactoryImpl
from coda.checks.checklist import CheckResult, CheckRun, CheckSuccessful
from coda.domain.fundingrequest import FundingRequest, FundingRequestId, TPublication
from coda.domain.publication import Monograph, Publication
from coda.domain.publication.publication import JournalId
from tests import domainfactory, modelfactory
from tests.fundingrequests.wizard.databuilders.article import ArticleRequestDataBuilder
from tests.fundingrequests.wizard.databuilders.monograph import MonographRequestDataBuilder
from tests.publications.test_publication_repository import assert_publication_eq


class PublicationCheckSpy:
    name = "Publication type check"
    params: dict[str, Any] = {}

    fundingrequest: FundingRequest[Any]

    @property
    def description(self) -> str:
        return "Check if publication type is valid"

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        assert isinstance(fundingrequest.publication, Publication)
        PublicationCheckSpy.fundingrequest = fundingrequest
        return CheckSuccessful()


class MonographCheckSpy:
    name = "Monograph check"
    params: dict[str, Any] = {}

    @property
    def description(self) -> str:
        return "Check if publication type is monograph"

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        assert isinstance(fundingrequest.publication, Monograph)
        return CheckSuccessful()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("get_builder", "expected_check_name"),
    [
        (lambda: ArticleRequestDataBuilder(), PublicationCheckSpy.name),
        (lambda: MonographRequestDataBuilder(), MonographCheckSpy.name),
    ],
)
def test__given_fundingrequest__run_checks__runs_checks_for_publication_type(
    get_builder: Callable[[], ArticleRequestDataBuilder | MonographRequestDataBuilder],
    expected_check_name: str,
) -> None:
    builder = get_builder()
    fundingrequest_id = fundingrequests.create_fundingrequest(builder.creation_dto())

    checkfactory = CheckFactoryImpl()
    checkfactory.register(Publication, PublicationCheckSpy)
    checkfactory.register(Monograph, MonographCheckSpy)

    checkruns = checks.run_checks(fundingrequest_id, checkfactory=checkfactory)

    checkruns_casted = cast(list[CheckRun], list(checkruns))
    assert len(checkruns_casted) == 1

    actual_check, *_ = checkruns_casted
    assert actual_check.check.name == expected_check_name


@pytest.mark.django_db
def test__creating_fundingrequest__runs_checks() -> None:
    checkfactory = CheckFactoryImpl()
    checkfactory.register(Publication, PublicationCheckSpy)
    builder = ArticleRequestDataBuilder()

    new_id = fundingrequests.create_fundingrequest(
        builder.creation_dto(), checkfactory=checkfactory
    )

    checkruns = checks.get_checkrun(new_id, checkfactory=checkfactory)
    assert checkruns is not None

    checkruns_casted = cast(list[CheckRun], list(checkruns))
    assert len(checkruns_casted) == 1

    actual_check, *_ = checkruns_casted
    assert actual_check.check.name == PublicationCheckSpy.name


@pytest.mark.django_db
def test__updating_fundingrequest_publication_meta__reruns_checks_with_updated_request() -> None:
    checkfactory = CheckFactoryImpl()
    checkfactory.register(Publication, PublicationCheckSpy)
    builder = ArticleRequestDataBuilder()
    new_id = fundingrequests.create_fundingrequest(builder.creation_dto())

    updated_builder = builder.with_contracts(builder.contract_years)
    dto = PublicationDto.from_publication(updated_builder.publication)
    metadata = UpdatePublicationMetadataCommand(
        meta=dto.meta,
        relevant_authors=dto.relevant_authors,
        other_authors=dto.other_authors,
        links=dto.links,
    )
    fundingrequests.update_publication_metadata(new_id, metadata, checkfactory=checkfactory)

    actual_publication = PublicationCheckSpy.fundingrequest.publication
    assert_publication_eq(actual_publication, updated_builder.expected.publication)


@pytest.mark.django_db
def test__updating_fundingrequest_publication_contracts__reruns_checks_with_updated_request() -> (
    None
):
    checkfactory = CheckFactoryImpl()
    checkfactory.register(Publication, PublicationCheckSpy)
    builder = ArticleRequestDataBuilder()
    new_id = fundingrequests.create_fundingrequest(builder.creation_dto())

    new_contract = domainfactory.contract()
    new_contract.id = contract_repository.create(new_contract)
    contract_year = new_contract.in_first_year()
    contract_dtos = [ContractYearDto.from_contract_year(contract_year)]
    new_journal = JournalId(modelfactory.journal().pk)

    fundingrequests.update_publication_journal_and_contracts(
        new_id, new_journal, contract_dtos, checkfactory=checkfactory
    )

    actual_publication: Publication = PublicationCheckSpy.fundingrequest.publication
    assert list(actual_publication.contracts) == [contract_year]
    assert actual_publication.journal == new_journal


@pytest.mark.django_db
def test__updating_fundingrequest_funding__reruns_checks_with_updated_request() -> None:
    checkfactory = CheckFactoryImpl()
    checkfactory.register(Publication, PublicationCheckSpy)
    new_id = save_request()

    updated_builder = ArticleRequestDataBuilder()
    fundingrequests.update_funding(
        new_id,
        updated_builder.cost_dto(),
        updated_builder.external_funding_dto(),
        checkfactory=checkfactory,
    )

    actual_cost = PublicationCheckSpy.fundingrequest.estimated_cost
    actual_external_funding = PublicationCheckSpy.fundingrequest.external_funding

    assert actual_cost == updated_builder.expected.estimated_cost
    assert actual_external_funding == updated_builder.expected.external_funding


def save_request() -> FundingRequestId:
    builder = ArticleRequestDataBuilder()
    new_id = fundingrequests.create_fundingrequest(builder.creation_dto())

    return new_id
