"""Tests for funding request list query service."""

import datetime

import pytest
from pytest_django import DjangoAssertNumQueries

from coda.apps.contracts import repository as contract_repository
from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.queries import list as list_query
from coda.apps.fundingrequests.queries.models import CoveredByContractDetail, FundingRequestListItem
from coda.apps.fundingrequests.services.labels import label_attach, label_create
from coda.apps.publications.models import AttachedContract
from coda.domain.color import Color
from coda.domain.contract import PublicationBilling
from coda.domain.date import DateRange
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__get_list_items__empty_queryset__returns_empty_list() -> None:
    """Verify empty queryset returns empty list."""
    queryset = FundingRequestModel.objects.none()

    items = list_query.get_list_items(queryset)

    assert len(items) == 0


@pytest.mark.django_db
def test__get_list_items__returns_correct_count() -> None:
    """Verify list items count matches input queryset."""
    modelfactory.fundingrequest()
    modelfactory.fundingrequest()
    queryset = FundingRequestModel.objects.all()

    items = list_query.get_list_items(queryset)

    assert len(items) == 2


@pytest.mark.django_db
def test__get_list_items__returns_list_item_instances() -> None:
    """Verify returned items are FundingRequestListItem instances."""
    modelfactory.fundingrequest()
    queryset = FundingRequestModel.objects.all()

    items = list_query.get_list_items(queryset)

    assert all(isinstance(item, FundingRequestListItem) for item in items)


@pytest.mark.django_db
def test__get_list_items__article__includes_journal_and_publisher() -> None:
    """Article items should include journal name and publisher."""
    fr = modelfactory.fundingrequest()
    queryset = FundingRequestModel.objects.filter(pk=fr.pk)

    items = list_query.get_list_items(queryset)

    assert len(items) == 1
    item = items[0]
    assert item.type == "Article"
    assert item.publishing_entity_type == "Journal"
    assert item.publishing_entity_name is not None
    assert item.publishing_entity_url is not None
    assert item.journal_publisher_name is not None
    assert item.journal_publisher_url is not None


@pytest.mark.django_db
def test__get_list_items__includes_basic_fields() -> None:
    """Items should include all basic required fields."""
    fr = modelfactory.fundingrequest()
    queryset = FundingRequestModel.objects.filter(id=fr.pk)

    items = list_query.get_list_items(queryset)

    item = items[0]
    assert item.id == fr.pk
    assert item.url == fr.get_absolute_url()
    assert item.publication_title == fr.publication.title
    assert isinstance(item.authors, list)
    assert item.updated_at == fr.updated_at.date()
    assert item.status == fr.review.review_result


@pytest.mark.django_db
def test__get_list_items__includes_payment_status() -> None:
    """Items should include payment status."""
    fr = modelfactory.fundingrequest()
    queryset = FundingRequestModel.objects.filter(id=fr.pk)

    items = list_query.get_list_items(queryset)

    assert items[0].payment_status is not None


@pytest.mark.django_db
def test__get_list_items__authors_are_strings() -> None:
    """Authors should be list of name strings, not objects."""
    fr = modelfactory.fundingrequest()
    queryset = FundingRequestModel.objects.filter(id=fr.pk)

    items = list_query.get_list_items(queryset)

    assert isinstance(items[0].authors, list)
    assert all(isinstance(author, str) for author in items[0].authors)
    assert len(items[0].authors) > 0


@pytest.mark.django_db
def test__get_list_items__with_labels() -> None:
    """Items should include labels."""
    fr = modelfactory.fundingrequest()
    label = label_create("Test Label", Color())
    label_attach(fr, label)

    queryset = FundingRequestModel.objects.filter(id=fr.pk)

    items = list_query.get_list_items(queryset)

    labels = list(items[0].labels)
    assert len(labels) == 1
    assert labels[0].name == "Test Label"


@pytest.mark.django_db
def test__get_list_items__with_consolidated_billing_contract() -> None:
    """Items with consolidated billing contracts show correct payment status."""
    from coda.apps.contracts.models import Contract
    from coda.apps.publications.models import AttachedContract

    # Create funding request
    fr = modelfactory.fundingrequest()

    # Create consolidated billing contract
    contract = Contract.objects.create(
        name="Test Consolidated Contract",
        start_date="2024-01-01",
        end_date="2025-12-31",
        publication_billing=PublicationBilling.Consolidated.value,
    )

    # Attach contract to publication
    AttachedContract.objects.create(
        publication=fr.publication, contract=contract, contract_year=2024
    )

    queryset = FundingRequestModel.objects.filter(id=fr.pk)

    items = list_query.get_list_items(queryset)

    assert isinstance(items[0].payment_status, CoveredByContractDetail)
    assert items[0].payment_status.status == "Covered by contract"
    assert items[0].payment_status.contract_name == "Test Consolidated Contract"


@pytest.mark.django_db
def test__get_list_items__with_invoice_payment() -> None:
    """Items with invoice payments show correct payment status."""
    from coda.apps.fundingrequests.queries.models import IndividuallyPaidDetail
    from coda.apps.publications.models import PublicationPayment

    fr = modelfactory.fundingrequest()
    invoice = modelfactory.invoice()

    # Create payment record
    PublicationPayment.objects.create(publication=fr.publication, invoice=invoice, status="paid")

    queryset = FundingRequestModel.objects.filter(id=fr.pk)

    items = list_query.get_list_items(queryset)

    assert isinstance(items[0].payment_status, IndividuallyPaidDetail)
    assert items[0].payment_status.status == "Paid"


@pytest.mark.django_db
def test__get_list_items__with_invoice_received() -> None:
    """Items with invoice received show correct payment status."""
    from coda.apps.fundingrequests.queries.models import InvoiceReceivedDetail
    from coda.apps.publications.models import PublicationPayment

    fr = modelfactory.fundingrequest()
    invoice = modelfactory.invoice()

    # Create payment record
    PublicationPayment.objects.create(
        publication=fr.publication, invoice=invoice, status="invoice_received"
    )

    queryset = FundingRequestModel.objects.filter(id=fr.pk)

    items = list_query.get_list_items(queryset)

    assert isinstance(items[0].payment_status, InvoiceReceivedDetail)
    assert items[0].payment_status.status == "Invoice received"


@pytest.mark.django_db
def test__get_list_items__query_count_is_constant(
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    """Verify query count doesn't grow with number of items (no N+1)."""
    # Create 10 funding requests
    for _ in range(10):
        modelfactory.fundingrequest()

    # Need to use optimized queryset like the view does
    queryset = (
        FundingRequestModel.objects.all()
        .select_related(
            "review",
            "publication__article_journal",
            "publication__article_journal__publisher",
            "publication__monograph_publisher",
        )
        .prefetch_related(
            "labels",
            "publication__relevant_authors",
            "publication__attached_contracts__contract",
        )
    )

    # Actual query count: 6 queries (optimal!)
    # 1. Fetch funding requests with joins (input queryset evaluation)
    # 2. Prefetch labels (from prefetch_related)
    # 3. Prefetch authors (from prefetch_related)
    # 4. Prefetch contracts for validation (from prefetch_related - NEW!)
    # 5. Bulk fetch contracts for payment status (with select_related for contract details)
    # 6. Bulk fetch payments (with select_related for invoice details)
    with django_assert_num_queries(6):
        items = list_query.get_list_items(queryset)
        # Force evaluation of lazy fields
        for item in items:
            _ = item.id
            _ = list(item.labels)  # Force queryset evaluation


@pytest.mark.django_db
def test__get_list_items__with_valid_contract_year__no_warning() -> None:
    """Verify no warning shown when contract year is valid."""

    # Create contract with period 2023-2025
    contract = domainfactory.contract(
        period=DateRange.create(start=datetime.date(2023, 1, 1), end=datetime.date(2025, 12, 31))
    )
    contract.id = contract_repository.create(contract)

    # Create funding request
    fr = modelfactory.fundingrequest()

    # Attach valid contract year (2024 - within period)

    contract_model = Contract.objects.get(id=contract.id)
    AttachedContract.objects.create(
        publication=fr.publication, contract=contract_model, contract_year=2024
    )

    queryset = FundingRequestModel.objects.all()
    items = list_query.get_list_items(queryset)

    assert len(items) == 1
    assert items[0].has_invalid_contract_years is False


@pytest.mark.django_db
def test__get_list_items__with_invalid_contract_year__shows_warning() -> None:
    """Verify warning shown when contract year is outside period."""
    contract = domainfactory.contract(
        period=DateRange.create(start=datetime.date(2023, 1, 1), end=datetime.date(2025, 12, 31))
    )
    contract.id = contract_repository.create(contract)

    fr = modelfactory.fundingrequest()

    contract_model = Contract.objects.get(id=contract.id)
    invalid_year = 2026
    AttachedContract.objects.create(
        publication=fr.publication, contract=contract_model, contract_year=invalid_year
    )

    queryset = FundingRequestModel.objects.all()
    items = list_query.get_list_items(queryset)

    assert len(items) == 1
    assert items[0].has_invalid_contract_years is True


@pytest.mark.django_db
def test__get_list_items__with_mixed_contract_years__shows_warning() -> None:
    """Verify warning shown when ANY contract year is invalid."""
    contract = domainfactory.contract(
        period=DateRange.create(start=datetime.date(2023, 1, 1), end=datetime.date(2025, 12, 31))
    )
    contract.id = contract_repository.create(contract)

    fr = modelfactory.fundingrequest()

    from coda.apps.contracts.models import Contract

    contract_model = Contract.objects.get(id=contract.id)

    valid_year = 2024
    AttachedContract.objects.create(
        publication=fr.publication, contract=contract_model, contract_year=valid_year
    )

    invalid_year = 2026
    AttachedContract.objects.create(
        publication=fr.publication, contract=contract_model, contract_year=invalid_year
    )

    queryset = FundingRequestModel.objects.all()
    items = list_query.get_list_items(queryset)

    assert len(items) == 1
    assert items[0].has_invalid_contract_years is True


@pytest.mark.django_db
def test__get_list_items__without_contracts__no_warning() -> None:
    """Verify no warning when publication has no contracts."""
    modelfactory.fundingrequest()

    queryset = FundingRequestModel.objects.all()
    items = list_query.get_list_items(queryset)

    assert len(items) == 1
    assert items[0].has_invalid_contract_years is False
