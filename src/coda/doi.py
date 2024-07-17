import re
from typing import Any

from coda.string import NonEmptyStr


class Doi:
    __match_args__ = ("_doi",)

    def __init__(self, doi: str) -> None:
        self._doi = NonEmptyStr(doi).strip()
        if not self._valid():
            raise ValueError("Invalid DOI format")

    @property
    def type(self) -> str:
        return "DOI"

    def _valid(self) -> bool:
        """
        These regex patterns are from the Crossref documentation:
        https://www.crossref.org/blog/dois-and-matching-regular-expressions/
        """
        return any(
            (
                re.match(r"^10.\d{4,9}/[-._;()/:A-Z0-9]+$", self._doi, re.IGNORECASE),
                re.match(
                    r"^10.\d{4}/\d+-\d+X?(\d+)\d+<[\d\w]+:[\d\w]*>\d+.\d+.\w+;\d$",
                    self._doi,
                    re.IGNORECASE,
                ),
                re.match(r"^10.1021/\w\w\d++$", self._doi, re.IGNORECASE),
                re.match(r"^10.1207/[\w\d]+\&\d+_\d+$", self._doi, re.IGNORECASE),
            )
        )

    @property
    def prefix(self) -> str:
        return self._doi.split("/")[0]

    @property
    def suffix(self) -> str:
        return self._doi.split("/")[1]

    @property
    def url(self) -> str:
        return f"https://doi.org/{str(self)}"

    def __str__(self) -> str:
        return self._doi

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Doi):
            return False
        return self._doi == other._doi

    def __hash__(self) -> int:
        return hash((self._doi,))
