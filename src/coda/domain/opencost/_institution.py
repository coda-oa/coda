from enum import Enum

from pydantic import BaseModel

from ._types import NonEmptyString
from ._validators import EitherFieldMixin


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


class InstitutionType(EitherFieldMixin):
    either_fields = ("name", "id")
    name: list[InstitutionName] | None = None
    id: list[InstitutionId] | None = None
