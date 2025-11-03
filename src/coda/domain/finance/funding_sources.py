from dataclasses import dataclass

from coda.domain.author import InstitutionId
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.string import NonEmptyStr


@dataclass
class Budget:
    id: FundingSourceId | None
    name: NonEmptyStr

    @classmethod
    def new(cls, name: str) -> "Budget":
        return cls(None, NonEmptyStr(name))


@dataclass
class SplitSource:
    id: FundingSourceId | None
    institution: InstitutionId
    institution_name: str

    @classmethod
    def new(cls, institution: InstitutionId, institution_name: str) -> "SplitSource":
        return cls(None, institution, institution_name)

    @property
    def name(self) -> str:
        return self.institution_name
