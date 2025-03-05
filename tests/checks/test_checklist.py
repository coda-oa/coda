import datetime

from coda.checks.checklist import (
    Check,
    CheckFailed,
    CheckRun,
    Checklist,
    CheckResult,
    CheckSuccessful,
)
from coda.fundingrequest.fundingrequest import FundingRequest
from coda.publication.publication import Publication
from tests import domainfactory


class CheckSpy(Check[Publication]):
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

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def __call__(self, fundingrequest: FundingRequest[Publication]) -> CheckResult:
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


def run(checklist: Checklist[Publication], now: datetime.datetime) -> list[CheckRun[Publication]]:
    fundingrequest = domainfactory.fundingrequest()
    return list(checklist.run(fundingrequest, now))


def test__running_checklist_with_no_checks_returns_empty_list() -> None:
    checklist = Checklist[Publication]()
    assert run(checklist, datetime.datetime.now()) == []


def test__running_checklist_with_successful_check__returns_success_result() -> None:
    now = datetime.datetime.now()
    check = successful_check(now)
    checklist = Checklist[Publication]()
    checklist.add_check(check)

    expected = CheckRun(check, now, check.result)
    assert run(checklist, now) == [expected]


def test__running_checklist_with_failing_check__returns_failure_result() -> None:
    now = datetime.datetime.now()
    check = failing_check(now)
    checklist = Checklist[Publication]()
    checklist.add_check(check)

    expected = CheckRun(check, now, check.result)
    assert run(checklist, now) == [expected]


def test__running_checklist_with_multiple_checks__returns_results_in_order() -> None:
    now = datetime.datetime.now()
    first = successful_check(now)
    second = failing_check(now)
    checklist = Checklist((first, second))

    first_run = CheckRun(first, now, first.result)
    second_run = CheckRun(second, now, second.result)
    assert run(checklist, now) == [first_run, second_run]


def test__adding_a_check__does_not_run_check() -> None:
    spy = successful_check(datetime.datetime.now())
    _ = Checklist([spy])

    assert not spy.was_called


def test__when_running_checklist__checks_are_yielded_in_order() -> None:
    now = datetime.datetime.now()
    spy1 = successful_check(now)
    spy2 = successful_check(now)
    checklist = Checklist((spy1, spy2))

    it = iter(checklist.run(domainfactory.fundingrequest(), now))

    next(it)
    assert spy1.was_called
    assert not spy2.was_called

    next(it)
    assert spy2.was_called
