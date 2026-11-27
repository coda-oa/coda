import abc
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from django.urls import reverse

from coda.apps.opencost.models import OpenCostReportContract, OpenCostReportPublication

logger = logging.getLogger(__name__)

type AnyOpenCostReportItem = OpenCostReportPublication | OpenCostReportContract


@dataclass
class ValidationWarning:
    level: Literal["error", "warning"]
    message: str
    entity_type: Literal["contract", "publication", "global"]
    entity_id: int | None = None
    entity_name: str | None = None
    fix_url: str | None = None


@dataclass(frozen=True)
class BaseWarning(abc.ABC):
    """Warning builders for snapshot data that cannot reach the XML."""

    entity_type: ClassVar[Literal["publication", "contract", "global"]]

    @staticmethod
    @abc.abstractmethod
    def url(item: "AnyOpenCostReportItem") -> str | None: ...

    @staticmethod
    @abc.abstractmethod
    def extract_entity_information(item: "AnyOpenCostReportItem") -> tuple[int, str]: ...

    @classmethod
    def create(
        cls,
        item: "AnyOpenCostReportItem",
        message: str,
        level: Literal["error", "warning"] = "error",
    ) -> ValidationWarning:
        entity_id, entity_name = cls.extract_entity_information(item)
        return ValidationWarning(
            level=level,
            message=message,
            entity_type=cls.entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            fix_url=cls.url(item),
        )


@dataclass(frozen=True)
class PublicationWarning(BaseWarning):
    entity_type: ClassVar[Literal["publication"]] = "publication"

    @staticmethod
    def url(item: "AnyOpenCostReportItem") -> str | None:
        """The request the publication was filed under, when it was filed under one at all."""
        if not isinstance(item, OpenCostReportPublication):
            raise TypeError("Expected OpenCostReportPublication")
        fundingrequest = getattr(item.publication, "fundingrequest", None)
        return (
            None
            if fundingrequest is None
            else reverse("fundingrequests:detail", kwargs={"pk": fundingrequest.id})
        )

    @staticmethod
    def extract_entity_information(item: "AnyOpenCostReportItem") -> tuple[int, str]:
        if not isinstance(item, OpenCostReportPublication):
            raise TypeError("Expected OpenCostReportPublication")
        return item.publication_id, item.title


@dataclass(frozen=True)
class ContractWarning(BaseWarning):
    entity_type: ClassVar[Literal["contract"]] = "contract"

    @staticmethod
    def url(item: "AnyOpenCostReportItem") -> str:
        if not isinstance(item, OpenCostReportContract):
            raise TypeError("Expected OpenCostReportContract")
        return reverse("contracts:detail", kwargs={"pk": item.contract_id})

    @staticmethod
    def extract_entity_information(item: "AnyOpenCostReportItem") -> tuple[int, str]:
        if not isinstance(item, OpenCostReportContract):
            raise TypeError("Expected OpenCostReportContract")
        return item.contract_id, item.contract.name


class GlobalWarning(BaseWarning):
    """Exclusions caused by globally configured data (institution settings).

    Entity identity is that of the item the warning is reported on; only the
    fix URL points at the global preferences.
    """

    entity_type: ClassVar[Literal["global"]] = "global"

    @staticmethod
    def url(item: "AnyOpenCostReportItem") -> str:
        _ = item
        return reverse("preferences:global_preferences")

    @staticmethod
    def extract_entity_information(item: "AnyOpenCostReportItem") -> tuple[int, str]:
        match item:
            case OpenCostReportPublication():
                return PublicationWarning.extract_entity_information(item)
            case OpenCostReportContract():
                return ContractWarning.extract_entity_information(item)


_WARNING_TYPES = {
    OpenCostReportContract: ContractWarning,
    OpenCostReportPublication: PublicationWarning,
}


@dataclass
class ReportItem:
    """One report row and the issues collected for it during transformation."""

    item: AnyOpenCostReportItem
    issues: list[ValidationWarning] = field(default_factory=list)

    def issue(
        self,
        message: str,
        level: Literal["error", "warning"] = "error",
    ) -> None:
        warning = _WARNING_TYPES[type(self.item)].create(self.item, message, level)
        self._record(warning)

    def global_issue(
        self,
        message: str,
        level: Literal["error", "warning"] = "error",
    ) -> None:
        self._record(GlobalWarning.create(self.item, message, level))

    def absorb(self, other: "ReportItem") -> None:
        """Merge issues for the same report row without logging them a second time."""
        if self.item != other.item:
            raise ValueError("Cannot absorb issues from a different report item")
        self.issues.extend(other.issues)

    def has_errors(self) -> bool:
        return any(issue.level == "error" for issue in self.issues)

    def _record(self, issue: ValidationWarning) -> None:
        if issue.level == "error":
            logger.warning("%s: %s", issue.entity_name, issue.message)
        else:
            logger.info("%s: %s", issue.entity_name, issue.message)
        self.issues.append(issue)

    def __iter__(self) -> Iterator[ValidationWarning]:
        return iter(self.issues)

    def __getitem__(self, index: int) -> ValidationWarning:
        return self.issues[index]

    def __len__(self) -> int:
        return len(self.issues)
