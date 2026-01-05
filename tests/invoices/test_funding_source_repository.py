import pytest

from coda.apps.invoices import funding_source_repository
from coda.domain.author import InstitutionId
from coda.domain.finance.funding_sources import Budget, SplitSource
from tests import modelfactory


@pytest.mark.django_db
def test__saving_a_budget__returns_budget_from_repository() -> None:
    sut = Budget.new("my budget")

    sut.id = funding_source_repository.create(sut)

    actual = funding_source_repository.get_by_id(sut.id)
    assert actual.id == sut.id
    assert actual.name == "my budget"


@pytest.mark.django_db
def test__saving_split_funding_source__returns_split_source_from_repository() -> None:
    institution = modelfactory.institution()
    institution_id = InstitutionId(institution.pk)

    sut = SplitSource.new(institution_id, institution.name)

    sut.id = funding_source_repository.create(sut)

    actual = funding_source_repository.get_by_id(sut.id)
    assert isinstance(actual, SplitSource)
    assert actual.id == sut.id
    assert actual.institution == institution_id
    assert actual.name == institution.name


@pytest.mark.django_db
def test__saving_split_source_with_same_institution__returns_same_id() -> None:
    institution = modelfactory.institution()
    institution_id = InstitutionId(institution.pk)

    sut = SplitSource.new(institution_id, institution.name)
    same_source = SplitSource.new(institution_id, institution.name)

    sut.id = funding_source_repository.create(sut)
    same_source.id = funding_source_repository.create(same_source)

    assert sut.id == same_source.id
