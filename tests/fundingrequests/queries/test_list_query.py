"""Tests for funding request list query service."""

import datetime

import pytest
from django.db.models import Prefetch
from pytest_django import DjangoAssertNumQueries

from coda.apps.contracts import repository as contract_repository
from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests import fundingrequest_query as fq
from coda.apps.fundingrequests import repository as fr_repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel, Label
from coda.apps.fundingrequests.queries import list as list_query
from coda.apps.fundingrequests.queries.models import CoveredByContractDetail, FundingRequestListItem
from coda.contexts.fundingrequest.services.labels import label_attach, label_create
from coda.apps.publications.models import AttachedContract
from coda.domain.color import Color
from coda.domain.contract import ContractYear, PublicationBilling
from coda.domain.date import DateRange
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId, FundingRequestId
from coda.domain.publication import JournalId
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
def test__get_list_items__labels_are_alphabetically_ordered() -> None:
    fr = modelfactory.fundingrequest()

    zebra = label_create("Zebra", Color())
    banana = label_create("Banana", Color())
    apple = label_create("Apple", Color())

    label_attach(fr, zebra)
    label_attach(fr, banana)
    label_attach(fr, apple)

    queryset = fq.search()
    items = list_query.get_list_items(queryset)

    item = next(item for item in items if item.id == fr.pk)
    label_names = [label.name for label in item.labels]

    assert label_names == ["Apple", "Banana", "Zebra"]


@pytest.mark.django_db
def test__get_list_items__with_consolidated_billing_contract() -> None:
    """Items with consolidated billing contracts show correct payment status."""
    fr = modelfactory.fundingrequest()

    contract = Contract.objects.create(
        name="Test Consolidated Contract",
        start_date="2024-01-01",
        end_date="2025-12-31",
        publication_billing=PublicationBilling.Consolidated.value,
    )

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
    for _ in range(10):
        modelfactory.fundingrequest()

    queryset = (
        FundingRequestModel.objects.all()
        .select_related(
            "review",
            "publication__article_journal",
            "publication__article_journal__publisher",
            "publication__monograph_publisher",
        )
        .prefetch_related(
            Prefetch("labels", queryset=Label.objects.order_by("name")),
            "publication__relevant_authors",
            "publication__attached_contracts__contract",
        )
    )

    with django_assert_num_queries(6):
        items = list_query.get_list_items(queryset)
        # Force evaluation of lazy fields
        for item in items:
            _ = item.id
            _ = list(item.labels)  # Force queryset evaluation


@pytest.mark.django_db
def test__get_list_items__with_valid_contract_year__no_warning() -> None:
    """Verify no warning shown when contract year is valid."""
    contract = domainfactory.contract(
        period=DateRange.create(start=datetime.date(2023, 1, 1), end=datetime.date(2025, 12, 31))
    )
    contract.id = contract_repository.create(contract)
    fr = modelfactory.fundingrequest()

    contract_model = Contract.objects.get(id=contract.id.pk)
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

    contract_model = Contract.objects.get(id=contract.id.pk)
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

    contract_model = Contract.objects.get(id=contract.id.pk)

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
def test__search_with_invalid_contract_year_criteria__filters_correctly() -> None:
    """Integration test: search criteria filters and list query converts correctly."""
    contract = domainfactory.contract(
        period=DateRange.create(start=datetime.date(2023, 1, 1), end=datetime.date(2025, 12, 31))
    )
    contract.id = contract_repository.create(contract)

    journal_id = JournalId(modelfactory.journal().pk)
    funding_org_id = FundingOrganizationId(modelfactory.funding_organization().pk)

    invalid_year_before = ContractYear(year=2022, contract=contract)
    pub_invalid_before = domainfactory.publication(journal_id, contracts=(invalid_year_before,))
    fr_invalid_before = domainfactory.fundingrequest(
        journal_id=journal_id, funding_org_id=funding_org_id
    )
    fr_invalid_before.publication = pub_invalid_before
    fr_invalid_before.id = fr_repository.create(fr_invalid_before)

    invalid_year_after = ContractYear(year=2026, contract=contract)
    pub_invalid_after = domainfactory.publication(journal_id, contracts=(invalid_year_after,))
    fr_invalid_after = domainfactory.fundingrequest(
        journal_id=journal_id, funding_org_id=funding_org_id
    )
    fr_invalid_after.publication = pub_invalid_after
    fr_invalid_after.id = fr_repository.create(fr_invalid_after)

    valid_year = contract.in_year(2024)
    pub_valid = domainfactory.publication(journal_id, contracts=(valid_year,))
    fr_valid = domainfactory.fundingrequest(journal_id=journal_id, funding_org_id=funding_org_id)
    fr_valid.publication = pub_valid
    fr_valid.id = fr_repository.create(fr_valid)

    fr_no_contract = domainfactory.fundingrequest(
        journal_id=journal_id, funding_org_id=funding_org_id
    )
    fr_no_contract.id = fr_repository.create(fr_no_contract)

    queryset = fq.search(fq.InvalidContractYearCriteria(show_only_invalid=True))
    items = list_query.get_list_items(queryset)

    assert len(items) == 2
    item_ids = {FundingRequestId(item.id) for item in items}
    assert fr_invalid_before.id in item_ids
    assert fr_invalid_after.id in item_ids

    for item in items:
        assert item.has_invalid_contract_years is True


@pytest.mark.django_db
def test__get_list_items__includes_publication_state() -> None:
    fr = modelfactory.fundingrequest()
    fr.publication.publication_state = "Published"
    fr.publication.online_publication_date = datetime.date(2023, 1, 1)
    fr.publication.save()

    queryset = FundingRequestModel.objects.filter(id=fr.pk)
    items = list_query.get_list_items(queryset)

    assert items[0].publication_state == "Published"
