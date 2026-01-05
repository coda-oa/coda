from dataclasses import dataclass, field
from typing import Literal

from coda.domain.author import InstitutionId
from coda.domain.finance.invoice import FundingSourceId


@dataclass
class Budget:
    id: FundingSourceId | None
    name: str = field(compare=False)

    @classmethod
    def new(cls, name: str) -> "Budget":
        return cls(None, name)

    def identity(self) -> FundingSourceId | None:
        return self.id

    def kind(self) -> Literal["budget"]:
        return "budget"


@dataclass
class SplitSource:
    id: FundingSourceId | None = field(compare=False)
    institution: InstitutionId
    institution_name: str = field(compare=False)

    @classmethod
    def new(cls, institution: InstitutionId, institution_name: str) -> "SplitSource":
        return cls(None, institution, institution_name)

    @property
    def name(self) -> str:
        return self.institution_name

    def identity(self) -> InstitutionId:
        return self.institution

    def kind(self) -> Literal["institution"]:
        return "institution"


type FundingSource = Budget | SplitSource
