import datetime
import random

from unittest.mock import create_autospec

from coda.fundingrequests import damm
from coda.fundingrequests.identity import PublicFundingRequestId


def test__a_fundingrequest_id__is_consists_of_coda__date_stamp__encoded_number__and__checksum() -> (
    None
):
    number = 247728699672827170
    unpadded_url_encoded_number = "A3Ab8JirFSI"
    damm_checksum = damm.checksum(number)

    rng = create_autospec(random.Random)
    rng.randint.return_value = number

    date = datetime.date(2021, 1, 1)
    date_str = "20210101"

    sut = PublicFundingRequestId.create(date, rng)

    actual = str(sut)

    assert sut.id() == f"{unpadded_url_encoded_number}{damm_checksum}"
    assert sut.date() == date
    assert actual == f"coda-{date_str}-{unpadded_url_encoded_number}{damm_checksum}"


def test__fundingrequest_id__can_be_constructed_from_string() -> None:
    number = 247728699672827170
    rng = create_autospec(random.Random)
    rng.randint.return_value = number
    date = datetime.date(2021, 1, 1)

    expected = PublicFundingRequestId.create(date, rng)
    actual = PublicFundingRequestId.from_str(str(expected))

    assert expected == actual
    assert expected.parts() == actual.parts()


def test__two_fundingrequest_ids__with_same_date_and_number__are_equal() -> None:
    rng = create_autospec(random.Random)
    rng.randint.return_value = 247728699672827170
    date = datetime.date(2021, 1, 1)

    first = PublicFundingRequestId.create(date, rng)
    second = PublicFundingRequestId.create(date, rng)

    assert first == second
    assert hash(first) == hash(second)


def test__two_fundingrequest_ids__with_same_date_and_different_number__are_not_equal() -> None:
    rng = create_autospec(random.Random)
    rng.randint.side_effect = [247728699672827170, 247728699672827171]
    date = datetime.date(2021, 1, 1)

    first = PublicFundingRequestId.create(date, rng)
    second = PublicFundingRequestId.create(date, rng)

    assert first != second
    assert hash(first) != hash(second)


def test__two_fundingrequest_ids__with_different_date_and_same_number__are_not_equal() -> None:
    rng = create_autospec(random.Random)
    rng.randint.return_value = 247728699672827170
    date = datetime.date(2021, 1, 1)
    other_date = datetime.date(2021, 1, 2)

    first = PublicFundingRequestId.create(date, rng)
    second = PublicFundingRequestId.create(other_date, rng)

    assert first != second
    assert hash(first) != hash(second)
