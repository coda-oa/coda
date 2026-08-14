from typing import Self

from pydantic import BaseModel, model_validator

from ._contract import ContractType
from ._publication import PublicationType


class Data(BaseModel):
    publication: list[PublicationType] | None = None
    contract: list[ContractType] | None = None

    @model_validator(mode="after")
    def _at_least_one_publication_or_contract(self) -> Self:
        if not self.publication and not self.contract:
            raise ValueError(
                "at least one of 'publication' or 'contract' must be set"
            )
        return self
