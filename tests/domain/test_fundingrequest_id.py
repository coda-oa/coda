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

    sut = PublicFundingRequestId(date, rng)

    actual = str(sut)

    assert sut.id() == f"{unpadded_url_encoded_number}{damm_checksum}"
    assert sut.date() == date
    assert actual == f"coda-{date_str}-{unpadded_url_encoded_number}{damm_checksum}"
