import datetime

from coda.contexts.fundingrequest.dto.import_dtos import (
    FundingRequestImportDto,
    FundingRequestImportListDto,
    PublicationImportDto,
)
from coda.domain.publication import License, OpenAccessType
from tests.fundingrequests.fundingrequest_import.entitynames import (
    IMPORT_JOURNAL_ISSN,
    IMPORT_JOURNAL_NAME,
    IMPORT_PUBLISHER_NAME,
)

MINIMAL_FUNDINGREQUEST_IMPORT = FundingRequestImportListDto(
    requests=[
        FundingRequestImportDto(
            request_date=datetime.date(2025, 3, 19),
            publication=PublicationImportDto(
                title="My article",
                kind="article",
                license=License.CC_BY,
                eissn=str(IMPORT_JOURNAL_ISSN),
                journal_name=IMPORT_JOURNAL_NAME,
                publisher_name=IMPORT_PUBLISHER_NAME,
                open_access_type=OpenAccessType.Opt_in,
            ),
        )
    ]
)


def minimal_article_request_import() -> FundingRequestImportListDto:
    return MINIMAL_FUNDINGREQUEST_IMPORT.model_copy(deep=True)


def minimal_monograph_request_import() -> FundingRequestImportListDto:
    monograph_import = minimal_article_request_import()
    monograph_import.requests[0].publication.kind = "monograph"
    return monograph_import
