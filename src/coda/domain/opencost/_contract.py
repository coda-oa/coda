from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from ._common import NonEmptyString
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


class ContractCostType(Enum):
    publish = "publish"
    read = "read"
    vat = "vat"


class ContractSecondaryIdentifiersType(BaseModel):
    id: list[ContractSecondaryIdType]


DateFormat = Annotated[str, StringConstraints(pattern=r"[0-9]{4}(-[0-9]{2}){0,2}")]


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
