import base64
import datetime
import random
import struct
from typing import Self

from coda.domain.errors import DomainError
from coda.domain.fundingrequest import damm

# NOTE: the largest number that can be encoded in base64 with struct.pack("!Q", n)
ID_RANGE = (1, 18446744073709551615)


def _encode_number(number: int) -> str:
    b_id = struct.pack("!Q", number)
    encoded = base64.urlsafe_b64encode(b_id)
    padding_removed = encoded.rstrip(b"=")
    str_id = padding_removed.decode()
    return str_id


def _decode_base64_id(id: str) -> int:
    padding = "=" * (4 - len(id) % 4)
    padded_id = id + padding
    decoded = base64.urlsafe_b64decode(padded_id)
    int_id = int(struct.unpack("!Q", decoded)[0])
    return int_id


class InvalidFundingRequestId(DomainError):
    @classmethod
    def invalid(cls, request_id: str) -> Self:
        return cls(f"The funding request id {request_id} is invalid")

    @classmethod
    def invalid_checksum(cls, request_id: str) -> Self:
        return cls(f"The checksum of the funding request id {request_id} is invalid")


class PublicFundingRequestId:
    """
    Identifier for funding requests that consist of a prefix, a date, and a base64-encoded random number with a checksum.
    The ID is not guaranteed to be unique. The application needs to ensure that the ID is unused.
    """

    __slots__ = ("_id", "_date")

    @classmethod
    def from_str(cls, id_str: str) -> "PublicFundingRequestId":
        parts = id_str.split("-", maxsplit=2)
        if len(parts) != 3 or parts[0] != "coda":
            raise InvalidFundingRequestId.invalid(id_str)

        date = datetime.datetime.strptime(parts[1], "%Y%m%d").date()
        id_without_checksum = parts[2][:-1]
        checksum = parts[2][-1]
        full_id = int(str(_decode_base64_id(id_without_checksum)) + checksum)
        if not damm.validate(full_id):
            raise InvalidFundingRequestId.invalid_checksum(id_str)

        return cls(date, id_without_checksum)

    @classmethod
    def create(
        cls, date: datetime.date | None = None, rng: random.Random | None = None
    ) -> "PublicFundingRequestId":
        rng = rng or random.Random()
        date = date or datetime.date.today()

        num = rng.randint(*ID_RANGE)

        _id = _encode_number(num)
        _date = date
        return cls(_date, _id)

    def __init__(self, date: datetime.date, id_: str) -> None:
        self._date = date
        self._id = id_

    def parts(self) -> tuple[str, datetime.date, str]:
        return "coda", self.date(), self.id()

    def id(self) -> str:
        return f"{self._id}{damm.checksum(_decode_base64_id(self._id))}"

    def id_without_checksum(self) -> str:
        return self._id

    def date(self) -> datetime.date:
        return self._date

    def __str__(self) -> str:
        return f"coda-{self._date:%Y%m%d}-{self.id()}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PublicFundingRequestId):
            return NotImplemented

        return self.parts() == other.parts()

    def __hash__(self) -> int:
        return hash(self.parts())
