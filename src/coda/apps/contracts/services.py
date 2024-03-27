import datetime
from coda.apps.contracts.models import Contract
from coda.apps.publishers.models import Publisher


def contract_create(
    name: str,
    publishers: list[Publisher],
    start_date: datetime.date | None = None,
    end_date: datetime.date | None = None,
    now: datetime.date = datetime.date.today(),
) -> Contract:
    is_active = _determine_if_active(start_date, end_date, now)

    contract = Contract.objects.create(
        name=name, start_date=start_date, end_date=end_date, is_active=is_active
    )
    contract.publishers.set(publishers)
    return contract


def _determine_if_active(
    start_date: datetime.date | None, end_date: datetime.date | None, now: datetime.date
) -> bool:
    start_date = start_date or datetime.date.min
    end_date = end_date or datetime.date.max
    return start_date <= now <= end_date
