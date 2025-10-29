import datetime
from decimal import Decimal

from coda.apps.fundingrequests.services.importservice.dto import (
    AuthorImportDto,
    ConceptImportDto,
    ContractImportDto,
    CostEstimateImportDto,
    DecidedFundingImportDto,
    FundingRequestImportDto,
    FundingRequestImportListDto,
    LinkImportDto,
    PublicationImportDto,
    PublishingStateImportDto,
    ResearchFundingImportDto,
    ReviewImportDto,
    SeperateContactImportDto,
)
from coda.domain.author import Role
from coda.domain.fundingrequest import PaymentMethod, ReviewResult
from coda.domain.money import Currency
from coda.domain.publication import License, OpenAccessType
from tests.fundingrequests.fundingrequest_import.entitynames import (
    COAR_RESOURCE_TYPES_NAME,
    DFG_SUBJECT_CLASSIFICATION_NAME,
    IMPORT_CONTRACT_NAME,
    IMPORT_JOURNAL_ISSN,
    IMPORT_JOURNAL_NAME,
    IMPORT_PUBLISHER_NAME,
    IMPORT_RESEARCH_FUNDER_NAME,
)

FUNDINGREQUEST_IMPORT = FundingRequestImportListDto(
    requests=[
        FundingRequestImportDto(
            request_date=datetime.date(2025, 3, 19),
            legacy_request_id="the-legacy-id",
            review=ReviewImportDto(
                result=ReviewResult.Approved,
                funding=DecidedFundingImportDto(
                    amount=Decimal("1000.00"), currency=Currency.EUR.code
                ),
                remarks="Remarks from the reviewer",
            ),
            estimated_cost=CostEstimateImportDto(
                amount=Decimal("1000.00"),
                currency=Currency.EUR.code,
                payment_method=PaymentMethod.Unknown,
            ),
            research_funding=[
                ResearchFundingImportDto(
                    funder=IMPORT_RESEARCH_FUNDER_NAME,
                    project_id="123456",
                    project_name="My research project",
                )
            ],
            request_remarks="Request remarks from the author",
            seperate_contact=SeperateContactImportDto(
                name="Mr. Secretary", email="secretary@example.com"
            ),
            labels=["important", "external"],
            publication=PublicationImportDto(
                title="My article",
                kind="article",
                license=License.CC_BY,
                eissn=str(IMPORT_JOURNAL_ISSN),
                journal_name=IMPORT_JOURNAL_NAME,
                publisher_name=IMPORT_PUBLISHER_NAME,
                open_access_type=OpenAccessType.Gold,
                publishing_state=PublishingStateImportDto(
                    online_date=datetime.date(2025, 3, 19), state="published"
                ),
                authors=[
                    AuthorImportDto(
                        name="Alice Doe",
                        email="a.doe@example.com",
                        orcid="0000-0002-1825-0097",
                        affiliation="University of Example",
                        role=Role.CORRESPONDING_AUTHOR,
                    )
                ],
                subject_area=ConceptImportDto(
                    vocabulary_name=DFG_SUBJECT_CLASSIFICATION_NAME, name="Humanities"
                ),
                publication_type=ConceptImportDto(
                    vocabulary_name=COAR_RESOURCE_TYPES_NAME, name="journal article"
                ),
                links=[LinkImportDto(type="DOI", value="10.1234/5678")],
                contracts=[ContractImportDto(name=IMPORT_CONTRACT_NAME, year=2025)],
            ),
        )
    ]
)


def full_article_request_import() -> FundingRequestImportListDto:
    return FUNDINGREQUEST_IMPORT.model_copy(deep=True)


def full_monograph_request_import() -> FundingRequestImportListDto:
    request_list = FUNDINGREQUEST_IMPORT.model_copy(deep=True)
    request_list.requests[0].publication.kind = "monograph"
    return request_list
