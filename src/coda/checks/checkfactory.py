from dataclasses import dataclass, field
from typing import Final

from coda.checks.blockcheck import BlockCheck
from coda.checks.checklist import Check, Checklist
from coda.checks.doajcheck import DoajCheck
from coda.publication import BasePublication, Monograph, Publication, PublicationKind

CheckType = type[Check]


@dataclass
class CheckFactory:
    check_types: dict[type[BasePublication], dict[str, CheckType]] = field(default_factory=dict)

    def create(self, check_name: str) -> Check:
        for _, checks in self.check_types.items():
            if check_name in checks:
                return checks[check_name]()

        raise ValueError(f"Check {check_name} not registered")

    def register(self, publication_kind: type[PublicationKind], check_type: CheckType) -> CheckType:
        check_name = check_type.__name__
        publication_checks = self.check_types.setdefault(publication_kind, {})
        publication_checks[check_name] = check_type
        return check_type

    def checks_for(self, publication_kind: type[PublicationKind]) -> Checklist:
        checks = [check() for check in self.check_types.get(publication_kind, {}).values()]
        return Checklist(checks)

    def clear(self) -> None:
        self.check_types.clear()


checkfactory: Final = CheckFactory()
checkfactory.register(Publication, DoajCheck)
checkfactory.register(Publication, BlockCheck)

checkfactory.register(Monograph, BlockCheck)
