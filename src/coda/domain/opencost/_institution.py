from enum import Enum
from coda.domain.opencost._common import NonEmptyString


from pydantic import BaseModel


class InstitutionIdType(Enum):
    ror = "ror"
    isni = "isni"
    ringold = "ringold"


class InstitutionId(BaseModel):
    value: NonEmptyString
    type: InstitutionIdType


class InstitutionNameType(Enum):
    full = "full"
    short = "short"


class InstitutionName(BaseModel):
    value: NonEmptyString
    type: InstitutionNameType


class InstitutionType(BaseModel):
    name: list[InstitutionName] | None = None
    id: list[InstitutionId] | None = None
