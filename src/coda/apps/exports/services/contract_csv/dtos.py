import datetime

from pydantic import BaseModel
from coda.contexts.finance.dto.import_dtos import InvoiceImportDto


class ContractLinkDto(BaseModel):
    type: str
    value: str


class ContractDetailsDto(BaseModel):
    name: str
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    publishers: list[str] = []
    journals: list[str] = []
    publication_billing: str = "Individually"
    active: bool = True
    links: list[ContractLinkDto] = []


class ContractCSVExportDto(BaseModel):
    contract: ContractDetailsDto
    invoices: list[InvoiceImportDto]
