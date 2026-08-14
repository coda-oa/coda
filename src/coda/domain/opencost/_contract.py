from enum import Enum
from typing import Self

from pydantic import BaseModel, Field, model_validator

from ._types import NonEmptyString, DateFormat
from ._institution import InstitutionType
from ._invoice import ContractCostDataType


class ContractPrimaryIdentifierType(Enum):
    ESAC = "ESAC"


class ContractPrimaryIdentifier(BaseModel):
    value: NonEmptyString
    type: ContractPrimaryIdentifierType


class ContractSecondaryIdTypeEnum(Enum):
    oai = "oai"
    ezb = "ezb"
    local = "local"


class ContractSecondaryIdType(BaseModel):
    value: NonEmptyString
    type: ContractSecondaryIdTypeEnum


class ContractSecondaryIdentifiersType(BaseModel):
    id: list[ContractSecondaryIdType]

    @model_validator(mode="after")
    def _at_least_one_id(self) -> Self:
        if not self.id:
            raise ValueError("at least one 'id' must be set")
        return self


class ParticipationType(BaseModel):
    to: DateFormat
    from_: DateFormat = Field(..., alias="from")


class ContractType(BaseModel):
    contract_name: NonEmptyString
    institution: InstitutionType
    participation: ParticipationType
    primary_identifier: ContractPrimaryIdentifier
    secondary_identifiers: ContractSecondaryIdentifiersType | None = None
    cost_data: ContractCostDataType
