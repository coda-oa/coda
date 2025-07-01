from typing import Any

from coda.checks.checkfactory import CheckType
from coda.checks.checklist import Check, CheckResult, CheckWarning, Checklist
from coda.domain.fundingrequest import FundingRequest, TPublication
from coda.domain.publication import PublicationKind


class NullCheck:
    params: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return ""

    @property
    def description(self) -> str:
        return ""

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        return CheckWarning("This is a null check")

    def __str__(self) -> str:
        return ""


class NullCheckFactory:
    def create(self, check_name: str) -> Check:
        return NullCheck()

    def register(self, publication_kind: type[PublicationKind], check_type: CheckType) -> CheckType:
        return check_type

    def checks_for(self, publication_kind: type[PublicationKind]) -> Checklist:
        return Checklist()
