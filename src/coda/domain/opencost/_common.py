from typing import Annotated
from coda.domain.opencost._contract import ContractType
from coda.domain.opencost._publication import PublicationType


from pydantic import BaseModel, StringConstraints


class Data(BaseModel):
    publication: list[PublicationType] | None = None
    contract: list[ContractType] | None = None


NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
