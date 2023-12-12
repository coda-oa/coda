import enum
from typing import Iterable, Protocol


class CheckResult(enum.Enum):
    SUCCESS = enum.auto()
    FAILURE = enum.auto()


class Check(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def description(self) -> str:
        ...

    def __call__(self) -> CheckResult:
        ...


class Checklist:
    """
    Represents a checklist of checks to be performed.
    """

    def __init__(self, checks: Iterable[Check] = ()) -> None:
        self.checks: list[Check] = []

    def run(self) -> Iterable[CheckResult]:
        """
        Executes all the checks and returns a list of CheckResult objects.
        """
        return (check() for check in self.checks)

    def add_check(self, check: Check) -> None:
        """
        Adds a check to the list of checks.

        Args:
            check (Check): The check to be added.

        Returns:
            None
        """
        self.checks.append(check)
