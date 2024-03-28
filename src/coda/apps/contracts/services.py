from dataclasses import dataclass
import datetime
from coda.apps.contracts.models import Contract
from coda.apps.publishers.models import Publisher


@dataclass
class DateRange:
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None


def contract_create(
    name: str,
    publishers: list[Publisher],
    date_range: DateRange | None = None,
    now: datetime.date | None = None,
) -> Contract:
    now = now or datetime.date.today()
    date_range = date_range or DateRange()
    contract = Contract.objects.create(
        name=name, start_date=date_range.start_date, end_date=date_range.end_date
    )
    contract.publishers.set(publishers)
    return contract
