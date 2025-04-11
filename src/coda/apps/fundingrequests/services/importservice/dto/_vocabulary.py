import pydantic


class ConceptImportDto(pydantic.BaseModel):
    name: str = ""
    vocabulary_name: str = ""
