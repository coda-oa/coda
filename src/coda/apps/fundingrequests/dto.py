from typing import Annotated

from pydantic import AfterValidator

from coda.apps.dto import CodaBaseDto
from coda.fundingrequest import ExternalFunding, FundingOrganizationId, Payment, PaymentMethod
from coda.money import Currency, Money
from coda.string import NonEmptyStr


class PaymentDto(CodaBaseDto):
    """
    A serializable representation of a Payment object.

    Attributes:
        estimated_cost (float): The estimated cost of the payment.
        currency_code: str
        method (str): The method of payment.
    """

    amount: float
    currency: str
    method: str

    @classmethod
    def from_payment(cls, payment: Payment) -> "PaymentDto":
        """Creates a CostDto instance from a Payment object."""
        return cls(
            amount=payment.amount.amount,
            currency=payment.amount.currency.code,
            method=payment.method.value,
        )

    def to_payment(self) -> Payment:
        """Converts the CostDto instance to a Payment object."""
        return Payment(
            amount=Money(str(self.amount), Currency.from_code(self.currency)),
            method=PaymentMethod(self.method.lower()),
        )


class ExternalFundingDto(CodaBaseDto):
    """
    Data Transfer Object (DTO) for external funding information.

    Attributes:
        organization (FundingOrganizationId): The ID of the funding organization.
        project_id (Annotated[str, AfterValidator(NonEmptyStr)]): The ID of the project, validated to be a non-empty string.
        project_name (str): The name of the project.
    """

    organization: FundingOrganizationId
    project_id: Annotated[str, AfterValidator(NonEmptyStr)]
    project_name: str

    @classmethod
    def from_external_funding(cls, external_funding: ExternalFunding) -> "ExternalFundingDto":
        """Creates an instance of ExternalFundingDto from an ExternalFunding object."""
        return cls(
            organization=external_funding.organization,
            project_id=external_funding.project_id,
            project_name=external_funding.project_name,
        )

    def to_external_funding(self) -> ExternalFunding:
        """Converts the ExternalFundingDto instance to an ExternalFunding object."""
        return ExternalFunding(
            organization=self.organization,
            project_id=NonEmptyStr(self.project_id),
            project_name=self.project_name,
        )


class ReviewDto(CodaBaseDto):
    decided_funding_amount: float
    decided_funding_currency: str
    reviewer_remarks: str
