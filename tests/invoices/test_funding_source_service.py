import pytest

from coda.apps.invoices import funding_source_repository
from coda.contexts.finance.services.funding_source_service import resolve_funding_source
from coda.domain.author import InstitutionId
from coda.domain.finance.funding_sources import Budget, SplitSource
from tests import modelfactory


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
