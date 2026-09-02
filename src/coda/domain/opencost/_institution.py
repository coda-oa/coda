from enum import Enum
from typing import Self

from pydantic import BaseModel, model_validator

from ._types import NonEmptyString


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

    @model_validator(mode="after")
    def _at_least_one_name_or_id(self) -> Self:
        if not (self.name or self.id):
            raise ValueError("at least one of 'name' or 'id' must be set")
        return self
