import datetime
from typing import cast

import pytest
from django.template.response import TemplateResponse
from django.test import Client
from django.urls import reverse

from coda.apps.fundingrequests import repository as fundingrequest_repository
from coda.contexts.fundingrequest.dto.commands import (
    CreateFundingRequestDto,
    ExternalFundingDto,
    ExtraContactDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.contexts.fundingrequest.services import fundingrequests
from coda.apps.invoices.repository import create
from coda.apps.publications.dto import PublicationDto
from coda.contexts.finance.dto.detail_position_dtos import PositionDetailDto
from coda.domain.finance.invoice import CreditorId, Invoice
from coda.domain.finance.invoice_positions import Position
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId, FundingRequest
from coda.domain.publication.publication import JournalId, Publication
from tests import domainfactory, modelfactory


@pytest.mark.django_db
@pytest.mark.usefixtures("logged_in")
def test__invoice_with_publication_position__viewing_invoice_details__publication_position_has_funding_request_info(
    client: Client,
) -> None:
    fr = funding_request()
    publication_position = domainfactory.publication_position(fr.publication.id)
    invoice = invoice_with_position(publication_position)

    response = goto_invoice_detail_view(client, invoice.id.pk)

    actual_invoice = response.context["display_invoice"]
    first_position: PositionDetailDto = actual_invoice.positions[0]
    assert first_position.url == reverse("fundingrequests:detail", kwargs={"pk": fr.id})


def funding_request() -> FundingRequest[Publication]:
    journal = JournalId(modelfactory.journal().pk)
    funding_org = FundingOrganizationId(modelfactory.funding_organization().pk)
    fr = domainfactory.fundingrequest(journal_id=journal, funding_org_id=funding_org)
    fr.id = fundingrequests.create_fundingrequest(
        CreateFundingRequestDto(
            publication=PublicationDto.from_publication(fr.publication),
            payment=PaymentDto.from_payment(fr.estimated_cost),
            extra_information=ExtraInformationDto(
                extra_contact=ExtraContactDto.from_contact(fr.extra_contact),
                request_remarks=fr.request_remarks,
            ),
            funding=[
                ExternalFundingDto.from_external_funding(funding) for funding in fr.external_funding
            ],
            request_date=fr.request_date,
        )
    )
    return fundingrequest_repository.get_article_request(fr.id)


def invoice_with_position(position: Position) -> Invoice:
    creditor = modelfactory.creditor()
    invoice = Invoice.new(
        number="123",
        creditor=CreditorId(creditor.pk),
        date=datetime.date.today(),
        positions=[position],
        comment="A comment",
    )
    invoice.id = create(invoice)
    return invoice


def goto_invoice_detail_view(client: Client, invoice_id: int) -> TemplateResponse:
    return cast(TemplateResponse, client.get(reverse("invoices:detail", kwargs={"pk": invoice_id})))
