import datetime

import pytest

from coda.apps.invoices import funding_source_repository
from coda.domain.author import InstitutionId
from coda.domain.date import DateRange
from coda.domain.finance.funding_sources import Budget, SplitSource
from coda.domain.money import Currency, Money
from tests import modelfactory


@pytest.mark.django_db
def test__saving_a_budget__returns_budget_from_repository() -> None:
    sut = Budget.new("my budget")

    sut.id = funding_source_repository.create(sut)

    actual = funding_source_repository.get_by_id(sut.id)
    assert actual.id == sut.id
    assert actual.name == "my budget"


@pytest.mark.django_db
def test__saving_a_budget_with_accounting_attributes__round_trips_amount_period_and_rules() -> None:
    period = DateRange.create(start=datetime.date(2026, 1, 1), end=datetime.date(2026, 12, 31))
    sut = Budget.new(
        "DARK 2026",
        amount=Money("120000", Currency.EUR),
        period=period,
        allow_over=True,
        allowance=Money("5000", Currency.EUR),
    )

    sut.id = funding_source_repository.create(sut)

    actual = funding_source_repository.get_by_id(sut.id)
    assert actual.amount == Money("120000", Currency.EUR)
    assert actual.period == period
    assert actual.allow_over is True
    assert actual.allowance == Money("5000", Currency.EUR)


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
