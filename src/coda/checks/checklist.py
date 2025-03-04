import datetime
from dataclasses import dataclass
from typing import Any, Generic, Protocol
from collections.abc import Iterable

from coda.fundingrequest import FundingRequest, TPublication


@dataclass(frozen=True, slots=True)
class CheckSuccessful:
    data: Any = None


@dataclass(frozen=True, slots=True)
class CheckFailed:
    reason: str


CheckResult = CheckSuccessful | CheckFailed


@dataclass(frozen=True, slots=True)
class CheckRun(Generic[TPublication]):
    check: "Check[TPublication]"
    timestamp: datetime.datetime
    result: CheckResult


class Check(Protocol, Generic[TPublication]):
    @property
    def name(self) -> str:
        ...

    @property
    def description(self) -> str:
        ...

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        ...


class Checklist(Generic[TPublication]):
    """
    Represents a checklist of checks to be performed.
    """

    def __init__(self, checks: Iterable[Check[TPublication]] = ()) -> None:  # noqa: F821
        self.checks = list(checks)

    def run(
        self, fundingrequest: FundingRequest[TPublication], now: datetime.datetime | None = None
    ) -> Iterable[CheckRun[TPublication]]:
        """
        Executes all the checks and returns a list of CheckResult objects.
        """
        now = now or datetime.datetime.now()
        return (CheckRun(check, now, check(fundingrequest)) for check in self.checks)

    def add_check(self, check: Check[TPublication]) -> None:
        """
        Adds a check to the list of checks.

        Args:
            check (Check): The check to be added.

        Returns:
            None
        """
        self.checks.append(check)
