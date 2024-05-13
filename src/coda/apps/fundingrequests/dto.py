from typing import TypedDict

from coda.fundingrequest import ExternalFunding, FundingOrganizationId, Payment, PaymentMethod
from coda.money import Currency, Money
from coda.string import NonEmptyStr


class CostDto(TypedDict):
    estimated_cost: float
    estimated_cost_currency: str
    payment_method: str


class ExternalFundingDto(TypedDict):
    organization: int
    project_id: str
    project_name: str


def parse_external_funding(external_funding: ExternalFundingDto) -> ExternalFunding:
    return ExternalFunding(
        organization=FundingOrganizationId(external_funding["organization"]),
        project_id=NonEmptyStr(external_funding["project_id"]),
        project_name=external_funding["project_name"],
    )


def parse_payment(cost: CostDto) -> Payment:
    return Payment(
        amount=Money(str(cost["estimated_cost"]), Currency[cost["estimated_cost_currency"]]),
        method=PaymentMethod(cost["payment_method"].lower()),
    )
