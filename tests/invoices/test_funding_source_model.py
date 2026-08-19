from decimal import Decimal

import pytest

from coda.apps.invoices.models import FundingSource


@pytest.mark.django_db
def test__funding_source__can_store_budget_amount() -> None:
    sut = FundingSource.objects.create(name="EU Horizon", budget_amount=Decimal("50000.00"))

    sut.refresh_from_db()

    assert sut.budget_amount == Decimal("50000.00")


@pytest.mark.django_db
def test__funding_source__budget_amount_defaults_to_none() -> None:
    sut = FundingSource.objects.create(name="No budget set")

    assert sut.budget_amount is None
