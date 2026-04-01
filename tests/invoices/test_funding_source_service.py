import pytest
from django.utils import timezone

from coda.apps.institutions.models import Institution
from coda.apps.invoices import funding_source_repository, repository
from coda.contexts.finance.services import invoice_parser, invoice_service
from coda.contexts.finance.services.funding_source_service import (
    get_institutions_allowed_as_funding_source,
    resolve_funding_source,
)
from coda.domain.author import InstitutionId
from coda.domain.finance.funding_sources import Budget, SplitSource
from coda.domain.finance.invoice import CreditorId
from tests import domainfactory, modelfactory


@pytest.mark.django_db
def test__given_budget_funding_source__resolve_funding_source__returns_budget_id() -> None:
    budget = Budget.new("my budget")
    budget.id = funding_source_repository.create(budget)

    actual = resolve_funding_source(budget)

    assert actual.id == budget.id


@pytest.mark.django_db
def test__non_existing_funding_source__resolve_funding_source__raises_error() -> None:
    budget = Budget.new("")
    with pytest.raises(ValueError):
        _ = resolve_funding_source(budget)


@pytest.mark.django_db
def test__given_institution_source__resolve_funding_source__return_funding_source_id_for_institution() -> (
    None
):
    institution = modelfactory.institution()
    institution_source = SplitSource.new(InstitutionId(institution.pk), institution.name)
    institution_source.id = funding_source_repository.create(institution_source)

    actual = resolve_funding_source(institution_source)

    assert isinstance(actual, SplitSource)
    assert actual.id == institution_source.id
    assert actual.institution == institution_source.institution


@pytest.mark.django_db
def test__given_non_existing_institution_source__resolve_funding_source__creates_missing_source_implicitly() -> (
    None
):
    institution = modelfactory.institution()
    institution_source = SplitSource.new(InstitutionId(institution.pk), institution.name)

    actual = resolve_funding_source(institution_source)

    assert actual.id is not None
    fs = funding_source_repository.get_by_id(actual.id)
    assert isinstance(fs, SplitSource)
    assert fs.institution == institution.pk


@pytest.mark.django_db
def test__given_non_existing_institution_id__resolve_funding_source__raises_error() -> None:
    institution = InstitutionId(99)
    institution_source = SplitSource.new(institution, "fake")

    with pytest.raises(ValueError):
        _ = resolve_funding_source(institution_source)


@pytest.mark.django_db
def test__archived_institution__selecting_institution_funding_source__archived_institution_is_excluded_from_dropdown() -> (
    None
):
    active = Institution.objects.create(name="Active University")
    archived = Institution.objects.create(name="Archived University", archived_at=timezone.now())

    institutions_list = list(get_institutions_allowed_as_funding_source())

    assert active in institutions_list
    assert archived not in institutions_list


@pytest.mark.django_db
def test__existing_position_with_archived_institution__editing_invoice__archived_institution_remains_in_dropdown() -> (
    None
):
    institution = modelfactory.institution()
    institution_id = InstitutionId(institution.pk)

    creditor = modelfactory.creditor()
    invoice = domainfactory.invoice(creditor=CreditorId(creditor.pk))
    position = domainfactory.free_position()
    split_source = SplitSource.new(institution_id, institution.name)
    position.assign_remaining(split_source)
    invoice.positions = [position]
    invoice.id = invoice_service.save(invoice)

    institution.archived_at = timezone.now()
    institution.save()

    loaded_invoice = repository.get_by_id(invoice.id)
    position_dtos = [invoice_parser.position_to_dto(p) for p in loaded_invoice.positions]

    institutions_list = list(
        get_institutions_allowed_as_funding_source(for_positions=position_dtos)
    )

    archived_institution = Institution.all_objects.get(pk=institution.pk)
    assert archived_institution in institutions_list


@pytest.mark.django_db
def test__multiple_positions_with_different_archived_institutions__editing_invoice__all_archived_institutions_remain_in_dropdown() -> (
    None
):
    institution_1 = modelfactory.institution()
    institution_2 = modelfactory.institution()
    institution_id_1 = InstitutionId(institution_1.pk)
    institution_id_2 = InstitutionId(institution_2.pk)

    creditor = modelfactory.creditor()
    invoice = domainfactory.invoice(creditor=CreditorId(creditor.pk))

    position_1 = domainfactory.free_position()
    split_source_1 = SplitSource.new(institution_id_1, institution_1.name)
    position_1.assign_remaining(split_source_1)

    position_2 = domainfactory.free_position()
    split_source_2 = SplitSource.new(institution_id_2, institution_2.name)
    position_2.assign_remaining(split_source_2)

    invoice.positions = [position_1, position_2]
    invoice.id = invoice_service.save(invoice)

    institution_1.archived_at = timezone.now()
    institution_1.save()
    institution_2.archived_at = timezone.now()
    institution_2.save()

    loaded_invoice = repository.get_by_id(invoice.id)
    position_dtos = [invoice_parser.position_to_dto(p) for p in loaded_invoice.positions]

    institutions_list = list(
        get_institutions_allowed_as_funding_source(for_positions=position_dtos)
    )

    archived_institution_1 = Institution.all_objects.get(pk=institution_1.pk)
    archived_institution_2 = Institution.all_objects.get(pk=institution_2.pk)
    assert archived_institution_1 in institutions_list
    assert archived_institution_2 in institutions_list
