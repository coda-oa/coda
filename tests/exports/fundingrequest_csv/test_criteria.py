import pytest

from tests import domainfactory, modelfactory
from coda.contexts.finance.services import invoice_service
from coda.domain.finance.invoice import CreditorId, FundingSourceId
from coda.domain.publication.publication import PublicationId

from coda.apps.fundingrequests.models import FundingRequest
from coda.apps.invoices.models import FundingSource as FundingSourceModel
from coda.apps.fundingrequests.fundingrequest_query import (
    InvoiceFundingSourceCriteria,
)
from coda.apps.fundingrequests import fundingrequest_query
from coda.apps.fundingrequests.fundingrequest_query import FundingRequestSearchCriteria


def _create_invoice(funding_request: FundingRequest, budget_model: FundingSourceModel) -> None:
    position = domainfactory.publication_position(PublicationId(funding_request.publication.id))
    funding_source = domainfactory.budget(FundingSourceId(budget_model.pk))
    position.assign_remaining(funding_source)

    creditor = modelfactory.creditor()
    invoice = domainfactory.invoice(creditor=CreditorId(creditor.pk), positions=[position])
    invoice_service.save(invoice)


@pytest.mark.django_db
def test__funding_request_with_invoice__filtered_by_funding_source__returns_only_funding_requests_with_invoices_matching_funding_source() -> (
    None
):
    fr_a = modelfactory.fundingrequest(title="Funding Source A Invoice")
    budget_a = modelfactory.budget(name="Funding Source A")

    _create_invoice(fr_a, budget_a)

    fr_b = modelfactory.fundingrequest(title="Funding Source B Invoice")
    budget_b = modelfactory.budget(name="Funding Source B")

    _create_invoice(fr_b, budget_b)

    criteria = InvoiceFundingSourceCriteria(funding_source=FundingSourceId(budget_a.pk))
    results = fundingrequest_query.search(criteria).distinct()

    assert list(results) == [fr_a]


@pytest.mark.django_db
def test__combining_multiple_criteria__filters_funding_requests_correctly() -> None:
    fr1 = modelfactory.fundingrequest(title="FR 1")
    budget_x = modelfactory.budget(name="Budget X")

    _create_invoice(fr1, budget_x)

    fr2 = modelfactory.fundingrequest(title="FR 2")
    budget_y = modelfactory.budget(name="Budget Y")

    _create_invoice(fr2, budget_y)

    criteria: list[FundingRequestSearchCriteria] = [
        InvoiceFundingSourceCriteria(funding_source=FundingSourceId(budget_x.pk)),
    ]
    results = fundingrequest_query.search(*criteria).distinct()

    assert list(results) == [fr1]
