import random
from coda.fundingrequests import damm


def test__a_number_with_damm_checksum_appended__is_valid() -> None:
    i = random.randint(0, 1000)

    sut = damm.append_checksum(i)

    assert damm.validate(int(sut))


def test__a_number_with_incorrect_checksum_is_invalid() -> None:
    i = random.randint(0, 1000)

    sut = damm.append_checksum(i)
    last_digit = int(str(sut)[-1])

    invalid = int(str(sut)[:-1] + str(offset_digit(last_digit)))
    assert not damm.validate(invalid)


def offset_digit(last_digit: int) -> int:
    if last_digit < 9:
        last_digit += 1
    else:
        last_digit -= 1

    return last_digit
