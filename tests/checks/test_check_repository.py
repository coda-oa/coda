import datetime
from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from coda.apps.checklist import repository
from coda.apps.fundingrequests import repository as fundingrequest_repository
import coda.checks.checkfactory
from coda.checks.checklist import CheckFailed, CheckResult, CheckRun, CheckSuccessful
from coda.fundingrequest import (
    FundingOrganizationId,
    FundingRequest,
    FundingRequestId,
    TPublication,
)
from coda.publication import JournalId, Publication
from tests import domainfactory, modelfactory


@dataclass
class CheckStub:
    result: CheckResult = CheckFailed("Failed")
    name: str = "Some check"
    description: str = "Some description"
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def successful(cls) -> "CheckStub":
        check = cls(
            result=CheckSuccessful(message="Success Message", data={"some_data": "some_value"})
        )
        check.params = {"param1": "success_value"}
        return check

    @classmethod
    def failed(cls) -> "CheckStub":
        check = cls(result=CheckFailed("Failed"))
        check.params = {"param1": "failed_value"}
        return check

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        return self.result


@pytest.mark.django_db
def test__saving_checkrun_for_fundingrequest__get__returns_checkrun() -> None:
    checkfactory = coda.checks.checkfactory.CheckFactory()
    checkfactory.register(Publication, CheckStub)

    fundingrequest_id = create_fundingrequest()

    first_run = checkrun_for(fundingrequest_id, CheckStub.successful())
    second_run = checkrun_for(fundingrequest_id, CheckStub.failed())

    repository.save([first_run, second_run])

    checkruns = repository.get(fundingrequest_id, checkfactory)

    checkruns_casted = cast(list[CheckRun], list(checkruns))
    first_actual, second_actual = checkruns_casted
    assert_checkrun_eq(first_actual, first_run)
    assert_checkrun_eq(second_actual, second_run)


@pytest.mark.django_db
def test__given_saved_checkrun__saving_new_checkrun__overrides_old_checkrun() -> None:
    checkfactory = coda.checks.checkfactory.CheckFactory()
    checkfactory.register(Publication, CheckStub)

    fundingrequest_id = create_fundingrequest()
    run = checkrun_for(fundingrequest_id, CheckStub.successful())
    repository.save([run])

    new_run = checkrun_for(fundingrequest_id, CheckStub.failed())
    repository.save([new_run])

    checkruns = cast(list[CheckRun], list(repository.get(fundingrequest_id, checkfactory)))
    assert len(checkruns) == 1


def checkrun_for(fundingrequest_id: FundingRequestId, check: CheckStub) -> CheckRun:
    return CheckRun(
        check=check,
        timestamp=now(),
        result=check.result,
        fundingrequest=fundingrequest_id,
    )


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def create_fundingrequest() -> FundingRequestId:
    journal_id = JournalId(modelfactory.journal().id)
    funding_org = FundingOrganizationId(modelfactory.funding_organization().id)
    fundingrequest = domainfactory.fundingrequest(journal_id=journal_id, funding_org_id=funding_org)
    fundingrequest.id = fundingrequest_repository.save(fundingrequest)
    return fundingrequest.id


def assert_checkrun_eq(actual: CheckRun, expected: CheckRun) -> None:
    assert actual.check.name == expected.check.name
    assert actual.check.description == expected.check.description
    assert actual.check.params == expected.check.params
    assert actual.result == expected.result
    assert actual.timestamp == expected.timestamp
    assert actual.fundingrequest == expected.fundingrequest
