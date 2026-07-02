"""Command DTOs for fundingrequest context write operations.

These DTOs are used for creating and updating funding requests.
They maintain bidirectional conversion methods (from_*/to_*) for
test data builders and domain object conversion.
"""

import datetime
from collections.abc import Iterable
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field

from coda.apps.authors.dto import AuthorDto
from coda.apps.dto import CodaBaseDto, OptionalFromStr
from coda.apps.publications.dto import (
    LinkDto,
    MonographDto,
    PublicationDto,
    PublicationMetaDto,
)
from coda.domain.fundingrequest import (
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequestContact,
    NoContact,
    Payment,
    PaymentMethod,
)
from coda.domain.money import Currency, Money
from coda.domain.string import NonEmptyStr


class PaymentDto(CodaBaseDto):
    """
    A serializable representation of a Payment object.

    Attributes:
        estimated_cost (Decimal): The estimated cost of the payment.
        currency_code: str
        method (str): The method of payment.
        external_costsplitting (bool | None): Whether external cost splitting occurred.
    """

    amount: Decimal
    currency: str
    method: str
    external_costsplitting: OptionalFromStr[bool] = None

    @classmethod
    def empty(cls) -> "PaymentDto":
        return PaymentDto(
            amount=Decimal("0"),
            currency=Currency.EUR.code,
            method=PaymentMethod.Unknown.value,
        )

    @classmethod
    def from_payment(cls, payment: Payment) -> "PaymentDto":
        """Creates a CostDto instance from a Payment object."""
        return cls(
            amount=payment.amount.amount,
            currency=payment.amount.currency.code,
            method=payment.method.value,
            external_costsplitting=payment.external_costsplitting,
        )

    def to_payment(self) -> Payment:
        """Converts the CostDto instance to a Payment object."""
        return Payment(
            amount=Money(str(self.amount), Currency.from_code(self.currency)),
            method=PaymentMethod(self.method.lower()),
            external_costsplitting=self.external_costsplitting,
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


class ExtraContactDto(CodaBaseDto):
    """
    Data Transfer Object (DTO) for extra contact information.

    Attributes:
        name (str): The name of the contact.
        email (str): The email address of the contact.
    """

    name: str | None = None
    email: str | None = None

    @classmethod
    def from_contact(cls, contact: FundingRequestContact) -> "ExtraContactDto":
        """Creates an instance of ExtraContactDto from a FundingRequestContact object."""
        return cls(name=contact.name, email=contact.email)

    def to_contact(self) -> FundingRequestContact:
        """Converts the ExtraContactDto instance to a FundingRequestContact object."""
        if self.name and self.email:
            return FilledContact(name=NonEmptyStr(self.name), email=self.email)
        else:
            return NoContact


class ExtraInformationDto(CodaBaseDto):
    extra_contact: ExtraContactDto = Field(default_factory=ExtraContactDto)
    request_remarks: str = ""


class UpdateReviewDto(CodaBaseDto):
    decided_funding_amount: Decimal
    decided_funding_currency: str
    reviewer_remarks: str
    result: str


# Type alias for clarity when using UpdateReviewDto for creation
CreateReviewDto = UpdateReviewDto


class CreateFundingRequestDto(CodaBaseDto):
    publication: Annotated[PublicationDto | MonographDto, Field(discriminator="publication_kind")]
    payment: PaymentDto
    extra_information: ExtraInformationDto
    funding: Iterable[ExternalFundingDto] = ()
    request_date: datetime.date = Field(default_factory=datetime.date.today)
    legacy_request_id: str = ""
    review: CreateReviewDto | None = None


class UpdatePublicationMetadataCommand(CodaBaseDto):
    """Command for updating publication metadata.

    Used by both the service layer (for updating funding requests) and the
    view layer (for storing wizard step data). This shared DTO maintains
    consistency across application boundaries.
    """

    meta: PublicationMetaDto
    relevant_authors: list[AuthorDto]
    other_authors: list[str]
    links: list[LinkDto]
