from pydantic import BaseModel

from ._contract import ContractType
from ._publication import PublicationType


class Data(BaseModel):
    publication: list[PublicationType] | None = None
    contract: list[ContractType] | None = None
