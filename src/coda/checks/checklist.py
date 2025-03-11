import datetime
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from coda.fundingrequest import FundingRequest, FundingRequestId, TPublication


@dataclass(frozen=True, slots=True)
class CheckSuccessful:
    data: dict[str, str | int] = field(default_factory=dict)

    def is_successful(self) -> bool:
        return True

    def __bool__(self) -> bool:
        return True

    def __str__(self) -> str:
        return "Check successful"


@dataclass(frozen=True, slots=True)
class CheckFailed:
    reason: str

    def is_successful(self) -> bool:
        return False

    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        return f"Check failed: {self.reason}"


CheckResult = CheckSuccessful | CheckFailed


@dataclass(frozen=True, slots=True)
class CheckRun:
    check: "Check"
    timestamp: datetime.datetime
    result: CheckResult
    fundingrequest: FundingRequestId

    @property
    def check_name(self) -> str:
        return self.check.name

    @property
    def check_description(self) -> str:
        return self.check.description


@dataclass(frozen=True, slots=True)
class ChecklistRun:
    fundingrequest: FundingRequestId
    timestamp: datetime.datetime
    checkruns: Iterable[CheckRun]

    def __iter__(self) -> Iterator[CheckRun]:
        yield from (check for check in self.checkruns)


class Check(Protocol):
    params: dict[str, Any]

    @property
    def name(self) -> str:
        ...

    @property
    def description(self) -> str:
        ...

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        ...


class Checklist:
    """
    Represents a checklist of checks to be performed.
    """

    def __init__(self, checks: Iterable[Check] = ()) -> None:  # noqa: F821
        self.checks = list(checks)

    def run(
        self, fundingrequest: FundingRequest[TPublication], now: datetime.datetime | None = None
    ) -> ChecklistRun:
        """
        Executes all the checks and returns a list of CheckResult objects.
        """
        if fundingrequest.id is None:
            raise ValueError("Cannot run checks on a funding request without an id")

        now = now or datetime.datetime.now()
        return ChecklistRun(
            fundingrequest.id,
            now,
            [
                CheckRun(check, now, check(fundingrequest), fundingrequest.id)
                for check in self.checks
            ],
        )

    def add_check(self, check: Check) -> None:
        """
        Adds a check to the list of checks.

        Args:
            check (Check): The check to be added.

        Returns:
            None
        """
        self.checks.append(check)
