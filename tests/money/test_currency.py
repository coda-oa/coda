from coda.domain.money import Currency


def test__currency_choices__pairs_all_codes_with_display_labels() -> None:
    choices = Currency.choices()

    assert [code for code, _ in choices] == [c.code for c in Currency]
    assert ("EUR", "EUR - Euro") in choices
    assert ("JPY", "JPY - Yen") in choices
