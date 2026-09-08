from enum import Enum

from pydantic import BaseModel, Field

from ._institution import InstitutionType
from ._invoice import ContractCostDataType
from ._types import DateFormat, NonEmptyString
from ._validators import RequiredList


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
    id: RequiredList[ContractSecondaryIdType]


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
