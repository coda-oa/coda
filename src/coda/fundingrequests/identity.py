import base64
import datetime
import random
import struct
from functools import cache

from coda.fundingrequests import damm

# NOTE: the largest number that can be encoded in base64 with struct.pack("!Q", n)
ID_RANGE = (1, 18446744073709551615)


class PublicFundingRequestId:
    __slots__ = ("_id", "_date")

    def __init__(self, date: datetime.date | None = None, rng: random.Random | None = None) -> None:
        rng = rng or random.Random()
        date = date or datetime.date.today()

        num = rng.randint(*ID_RANGE)

        _id = self._encode_number(num)
        self._id = _id
        self._date = date

    def _encode_number(self, number: int) -> str:
        b_id = struct.pack("!Q", number)
        encoded = base64.urlsafe_b64encode(b_id)
        padding_removed = encoded.rstrip(b"=")
        str_id = padding_removed.decode()
        return str_id

    def parts(self) -> tuple[str, datetime.date, str]:
        return "coda", self.date(), self.id()

    @cache
    def id(self) -> str:
        return f"{self._id}{damm.checksum(self._decode_base64_id())}"

    def date(self) -> datetime.date:
        return self._date

    @cache
    def _decode_base64_id(self) -> int:
        padding = "=" * (4 - len(self._id) % 4)
        padded_id = self._id + padding
        decoded = base64.urlsafe_b64decode(padded_id)
        int_id = int(struct.unpack("!Q", decoded)[0])
        return int_id

    def __str__(self) -> str:
        return f"coda-{self._date:%Y%m%d}-{self.id()}"
