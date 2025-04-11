from typing import Annotated

import pydantic

from coda.domain import orcid
from coda.domain.author import Role

Orcid = Annotated[str, pydantic.PlainValidator(orcid.Orcid)]


class AuthorImportDto(pydantic.BaseModel):
    name: str
    email: str
    orcid: Orcid | None = None
    affiliation: str | None = None
    role: Role = Role.CO_AUTHOR
