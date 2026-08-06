from pydantic import BaseModel
from coda.contexts.fundingrequest.dto.import_dtos import FundingRequestImportDto
from coda.contexts.finance.dto.import_dtos import InvoiceImportDto


class FundingRequestExportDto(BaseModel):
    funding_request: FundingRequestImportDto
    invoices: list[InvoiceImportDto]
