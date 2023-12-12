from coda.checks import CheckResult, Checklist


class CheckSpy:
    def __init__(self, name: str, description: str, result: CheckResult) -> None:
        self.name = name
        self.description = description
        self.result = result
        self.was_called = False

    def __call__(self) -> CheckResult:
        self.was_called = True
        return self.result


def successful_check() -> CheckSpy:
    return CheckSpy("Test check", "Test description", CheckResult.SUCCESS)


def failing_check() -> CheckSpy:
    return CheckSpy("Test check", "Test description", CheckResult.FAILURE)


def run(checklist: Checklist) -> list[CheckResult]:
    return list(checklist.run())


def test__running_checklist_with_no_checks_returns_empty_list() -> None:
    checklist = Checklist()
    assert run(checklist) == []


def test__running_checklist_with_successful_check__returns_success_result() -> None:
    checklist = Checklist()
    checklist.add_check(successful_check())

    assert run(checklist) == [CheckResult.SUCCESS]


def test__running_checklist_with_failing_check__returns_failure_result() -> None:
    checklist = Checklist()
    checklist.add_check(failing_check())

    assert run(checklist) == [CheckResult.FAILURE]


def test__running_checklist_with_multiple_checks__returns_results_in_order() -> None:
    checklist = Checklist((successful_check(), failing_check()))

    assert run(checklist) == [CheckResult.SUCCESS, CheckResult.FAILURE]


def test__adding_a_check__does_not_run_check() -> None:
    spy = successful_check()
    _ = Checklist([spy])

    assert not spy.was_called


def test__when_running_checklist__checks_are_yielded_in_order() -> None:
    spy1 = successful_check()
    spy2 = successful_check()
    checklist = Checklist((spy1, spy2))

    it = iter(checklist.run())

    next(it)
    assert spy1.was_called
    assert not spy2.was_called

    next(it)
    assert spy2.was_called
