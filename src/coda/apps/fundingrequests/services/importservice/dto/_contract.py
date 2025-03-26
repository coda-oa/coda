import pydantic


class ContractImportDto(pydantic.BaseModel):
    name: str
    year: pydantic.PositiveInt
