"""Mapper functions for FundingRequest detail view models.

Maps Django ORM models to domain detail classes for use in detail views.
"""

from collections.abc import Iterable
from typing import Literal, TypedDict
from urllib.parse import urlencode

from django.urls import reverse

from coda.apps.fundingrequests.models import ExternalFunding as ExternalFundingModel
from coda.apps.fundingrequests.queries.models import (
    CoveredByContractDetail,
    ExternalFundingDetail,
    IndividuallyPaidDetail,
    InvoiceReceivedDetail,
    PublicationPaymentDetail,
    UnpaidDetail,
)
from coda.domain.publication.payment import (
    PublicationCoveredByContract,
    PublicationPayments,
    PublicationPaymentStatus,
)


class PublishingEntityInfo(TypedDict):
    """Publishing entity details extracted from funding request."""

    edit_url: str
    name: str
    identifier_name: str
    identifier: str
    type: Literal["Journal", "Publisher"]


def to_payment_details(
    payment_status: PublicationPaymentStatus, request_id: str
) -> PublicationPaymentDetail:
    """Convert PublicationPaymentStatus to appropriate PublicationPaymentDetails."""
    if isinstance(payment_status, PublicationCoveredByContract):
        return _to_contract_covered_details(payment_status)

    return _to_individual_payment_details(payment_status, request_id)


def to_external_funding_list(
    external_funding: Iterable[ExternalFundingModel],
) -> list[ExternalFundingDetail]:
    """Convert list of ExternalFunding models to ExternalFundingDetails."""
    return [_to_external_funding_details(ef) for ef in external_funding]


# ============================================================================
# PRIVATE CONVERSIONS
# ============================================================================


def _to_external_funding_details(ef: ExternalFundingModel) -> ExternalFundingDetail:
    return ExternalFundingDetail(
        organization=ef.organization.name,
        project_id=ef.project_id,
        project_name=ef.project_name,
    )


def _to_contract_covered_details(
    payment_status: PublicationCoveredByContract,
) -> CoveredByContractDetail:
    """Convert contract-covered payment status to details."""
    return CoveredByContractDetail(
        contract_id=str(payment_status.contract_id),
        contract_name=payment_status.contract_name,
        contract_year=str(payment_status.contract_year),
        url=reverse("contracts:detail", kwargs={"pk": payment_status.contract_id}),
    )


def _to_individual_payment_details(
    payment_status: PublicationPayments, request_id: str
) -> PublicationPaymentDetail:
    """Convert individual payment status to appropriate details type."""
    invoice_list_url = f"{reverse('invoices:list')}?{urlencode({'search_term': request_id})}"

    if not payment_status.payments():
        return UnpaidDetail()

    if payment_status.all_paid():
        return IndividuallyPaidDetail(url=invoice_list_url)

    if payment_status.has_pending_payments():
        return InvoiceReceivedDetail(url=invoice_list_url)

    return UnpaidDetail()
