from coda.apps.fundingrequests.dto import (
    ExternalFundingDto,
    ExtraContactDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.apps.fundingrequests.models import FundingOrganization
from coda.domain.fundingrequest import FundingOrganizationId

from ..dto import (
    CostEstimateImportDto,
    FundingRequestImportDto,
    ResearchFundingImportDto,
)


def parse_cost_estimate(import_dto: CostEstimateImportDto) -> PaymentDto:
    return PaymentDto(
        amount=import_dto.amount,
        currency=import_dto.currency,
        method=import_dto.payment_method.value,
    )


def parse_funding(import_dto: ResearchFundingImportDto) -> ExternalFundingDto:
    return ExternalFundingDto(
        organization=parse_funder(import_dto),
        project_id=import_dto.project_id,
        project_name=import_dto.project_name,
    )


def parse_funder(import_dto: ResearchFundingImportDto) -> FundingOrganizationId:
    org, _ = FundingOrganization.objects.get_or_create(name=import_dto.funder)
    return FundingOrganizationId(org.id)


def parse_extra_information(import_dto: FundingRequestImportDto) -> ExtraInformationDto:
    return ExtraInformationDto(
        request_remarks=import_dto.request_remarks,
        extra_contact=ExtraContactDto(
            name=import_dto.seperate_contact.name,
            email=import_dto.seperate_contact.email,
        ),
    )
