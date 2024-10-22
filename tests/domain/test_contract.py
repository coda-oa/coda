import datetime
from coda.contract import Contract, PublisherId
from coda.date import DateRange
from coda.string import NonEmptyStr

CONTRACT_NAME = NonEmptyStr("contract name")


def make_contract(date_range: DateRange) -> Contract:
    return Contract.new(
        CONTRACT_NAME,
        (PublisherId(1), PublisherId(2)),
        period=date_range,
    )


def test__contract_with_only_start_date__is_always_active_after_start_date() -> None:
    date_range = DateRange.create(start=datetime.date.min)
    sut = make_contract(date_range)

    assert sut.is_active(datetime.date.min) is True
    assert sut.is_active(datetime.date.max) is True


def test__contract__is_inactive_outside_date_range() -> None:
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    yesterday = today - datetime.timedelta(days=1)
    day_after_tomorrow = tomorrow + datetime.timedelta(days=1)

    date_range = DateRange(start=today, end=tomorrow)
    sut = make_contract(date_range)

    assert sut.is_active(today) is True
    assert sut.is_active(tomorrow) is True
    assert sut.is_active(yesterday) is False
    assert sut.is_active(day_after_tomorrow) is False
