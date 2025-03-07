import datetime
from typing import Any

from coda.checks.checklist import (
    CheckFailed,
    Checklist,
    ChecklistRun,
    CheckResult,
    CheckRun,
    CheckSuccessful,
)
from coda.fundingrequest import FundingRequest, FundingRequestId, TPublication
from tests import domainfactory

FUNDING_REQUEST_ID = FundingRequestId(1)


class CheckSpy:
    @classmethod
    def successful(cls, name: str, description: str) -> "CheckSpy":
        return cls(name, description, CheckSuccessful(None))

    @classmethod
    def failing(cls, name: str, description: str) -> "CheckSpy":
        return cls(name, description, CheckFailed("Failure reason"))

    def __init__(self, name: str, description: str, result: CheckResult) -> None:
        self._name = name
        self._description = description
        self.result = result
        self.was_called = False
        self.params: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        self.was_called = True
        return self.result


def successful_check(timestamp: datetime.datetime) -> CheckSpy:
    check_name = "Successful check"
    check_description = "Test description"
    return CheckSpy.successful(check_name, check_description)


def failing_check(timestamp: datetime.datetime) -> CheckSpy:
    check_name = "Test check"
    check_description = "Test description"
    return CheckSpy.failing(check_name, check_description)


def run(checklist: Checklist, now: datetime.datetime) -> ChecklistRun:
    fundingrequest = domainfactory.fundingrequest(id=FUNDING_REQUEST_ID)
    return checklist.run(fundingrequest, now)


def test__running_checklist_with_no_checks_returns_empty_list() -> None:
    checklist = Checklist()
    now = datetime.datetime.now()
    assert run(checklist, now) == ChecklistRun(FUNDING_REQUEST_ID, now, [])


def test__running_checklist_with_successful_check__returns_success_result() -> None:
    now = datetime.datetime.now()
    check = successful_check(now)
    checklist = Checklist()
    checklist.add_check(check)

    expected = CheckRun(check, now, check.result, FUNDING_REQUEST_ID)
    assert run(checklist, now) == ChecklistRun(FUNDING_REQUEST_ID, now, [expected])


def test__running_checklist_with_failing_check__returns_failure_result() -> None:
    now = datetime.datetime.now()
    check = failing_check(now)
    checklist = Checklist()
    checklist.add_check(check)

    expected = CheckRun(check, now, check.result, FUNDING_REQUEST_ID)
    assert run(checklist, now) == ChecklistRun(FUNDING_REQUEST_ID, now, [expected])


def test__running_checklist_with_multiple_checks__returns_results_in_order() -> None:
    now = datetime.datetime.now()
    first = successful_check(now)
    second = failing_check(now)
    checklist = Checklist((first, second))

    first_run = CheckRun(first, now, first.result, FUNDING_REQUEST_ID)
    second_run = CheckRun(second, now, second.result, FUNDING_REQUEST_ID)
    assert run(checklist, now) == ChecklistRun(FUNDING_REQUEST_ID, now, [first_run, second_run])


def test__adding_a_check__does_not_run_check() -> None:
    spy = successful_check(datetime.datetime.now())
    _ = Checklist([spy])

    assert not spy.was_called
