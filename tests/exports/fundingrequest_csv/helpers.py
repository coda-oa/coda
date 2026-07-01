from datetime import date
from typing import Any

from coda.apps.fundingrequests.fundingrequest_query import FundingRequestSearchParams
from coda.domain.date import DateRange


def _make_params(
    period_start: date,
    period_end: date,
    **kwargs: Any,
) -> FundingRequestSearchParams:
    return FundingRequestSearchParams(
        date_range=DateRange(period_start, period_end),
        **kwargs,
    )
