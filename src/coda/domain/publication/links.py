import re
from typing import Any, NamedTuple, Protocol

import pydantic

from coda.domain.errors import DomainError
from coda.domain.string import NonEmptyStr

from pydantic_core import PydanticCustomError
from pydantic_extra_types.isbn import ISBN


class Link(Protocol):
    def type(self) -> str:
        ...

    def value(self) -> str:
        ...

    def url(self) -> str | None:
        ...


class UserLink(NamedTuple):
    link_type: str
    link_value: str
    url_prefix: str = ""

    def type(self) -> str:
        return self.link_type

    def value(self) -> str:
        return self.link_value

    def url(self) -> str:
        return self.url_prefix + self.link_value

    def __str__(self) -> str:
        return self.link_value


class InvalidIsbn(DomainError):
    def __init__(self, isbn: str, *args: object) -> None:
        super().__init__(f"{isbn} is not a valid ISBN", *args)


class Isbn:
    __slots__ = ("_isbn",)
    __match_args__ = ("_isbn",)

    def __init__(self, isbn: str) -> None:
        try:
            raw_isbn = NonEmptyStr(isbn.replace("-", ""))
            ISBN.validate_isbn_format(raw_isbn)
            self._isbn = raw_isbn
        except PydanticCustomError:
            raise InvalidIsbn(isbn)

    @staticmethod
    def type() -> str:
        return "ISBN"

    def value(self) -> str:
        return self._isbn

    def url(self) -> str:
        """
        URL based on PICA interface documentation found at:
        https://github.com/pro4bib/pica/blob/master/schnittstellen.md#sru
        """
        return f"https://opac.k10plus.de/DB=2.299/CMD?ACT=SRCHA&IKT=7&TRM={self}"

    def is_isbn_10(self) -> bool:
        return len(self) == 10

    def is_isbn_13(self) -> bool:
        return len(self) == 13

    def to_isbn_13(self) -> "Isbn":
        if self.is_isbn_13():
            return self

        return Isbn(ISBN.convert_isbn10_to_isbn13(self._isbn))

    def __str__(self) -> str:
        return self._isbn

    def __len__(self) -> int:
        return len(self._isbn)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Isbn):
            return False

        return self._isbn == other._isbn

    def __hash__(self) -> int:
        return hash((self._isbn,))


class InvalidDoi(DomainError):
    def __init__(self, *args: object) -> None:
        super().__init__("Invalid DOI format", *args)


class Doi:
    __match_args__ = ("_doi",)

    def __init__(self, doi: str) -> None:
        self._doi = NonEmptyStr(doi).strip()
        if not self._valid():
            raise InvalidDoi()

    @staticmethod
    def type() -> str:
        return "DOI"

    def _valid(self) -> bool:
        """
        These regex patterns are from the Crossref documentation:
        https://www.crossref.org/blog/dois-and-matching-regular-expressions/
        """
        return any(
            (
                re.match(r"^10.\d{4,9}/[-._;()/:A-Z\d]+$", self._doi, re.IGNORECASE),
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

    def value(self) -> str:
        return self._doi

    def url(self) -> str:
        return f"https://doi.org/{self}"

    def __str__(self) -> str:
        return self._doi

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Doi):
            return False
        return self._doi == other._doi

    def __hash__(self) -> int:
        return hash((self._doi,))


class InvalidUrl(DomainError):
    def __init__(self, url: str, *args: object) -> None:
        super().__init__(f"{url} is not a valid URL", *args)


class Url:
    def __init__(self, url: str) -> None:
        try:
            self._url = str(pydantic.HttpUrl(url))
        except pydantic.ValidationError:
            raise InvalidUrl(f"{url} is not a valid URL")

    @staticmethod
    def type() -> str:
        return "URL"

    def value(self) -> str:
        return self._url

    def url(self) -> str:
        return self._url

    def __str__(self) -> str:
        return self._url

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Url):
            return False
        return self._url == other._url

    def __hash__(self) -> int:
        return hash((self._url,))


class InvalidPmid(DomainError):
    def __init__(self, message: str = "Invalid PMID format", *args: object) -> None:
        super().__init__(message, *args)


class Pmid:
    __match_args__ = ("_pmid",)

    def __init__(self, pmid: str) -> None:
        self._pmid = NonEmptyStr(pmid).strip()
        error_message = self._validate()
        if error_message:
            raise InvalidPmid(error_message)

    @staticmethod
    def type() -> str:
        return "PMID"

    def _validate(self) -> str | None:
        if not self._pmid.isdigit():
            return "Invalid PMID format: must contain only digits"
        return None

    def value(self) -> str:
        return self._pmid

    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self}/"

    def __str__(self) -> str:
        return self._pmid

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Pmid):
            return False
        return self._pmid == other._pmid

    def __hash__(self) -> int:
        return hash((self._pmid,))


class InvalidPmc(DomainError):
    def __init__(self, message: str = "Invalid PMC format", *args: object) -> None:
        super().__init__(message, *args)


class Pmc:
    __match_args__ = ("_pmc",)

    def __init__(self, pmc: str) -> None:
        normalized = NonEmptyStr(pmc).strip().upper()
        self._pmc = normalized
        error_message = self._validate()
        if error_message:
            raise InvalidPmc(error_message)

    @staticmethod
    def type() -> str:
        return "PMC"

    def _validate(self) -> str | None:
        if not self._pmc.startswith("PMC"):
            return "Invalid PMC format: must start with 'PMC'"

        number_part = self._pmc[3:]
        if not number_part:
            return "Invalid PMC format: must have digits after 'PMC'"

        if not number_part.isdigit():
            return "Invalid PMC format: must contain only digits after 'PMC'"

        return None

    def value(self) -> str:
        return self._pmc

    def url(self) -> str:
        return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{self}/"

    def __str__(self) -> str:
        return self._pmc

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Pmc):
            return False
        return self._pmc == other._pmc

    def __hash__(self) -> int:
        return hash((self._pmc,))


class InvalidHandle(DomainError):
    def __init__(self, message: str = "Invalid Handle format", *args: object) -> None:
        super().__init__(message, *args)


class Handle:
    """Handle System identifier validation.

    Format: prefix/suffix (e.g., 1234/5678 or 10.1234/5678)
    Also accepts: hdl:prefix/suffix or https://hdl.handle.net/prefix/suffix
    """

    __match_args__ = ("_handle",)

    def __init__(self, handle: str) -> None:
        normalized = NonEmptyStr(handle).strip()

        if normalized.lower().startswith("hdl:"):
            normalized = normalized[4:]

        for prefix in ["https://hdl.handle.net/", "http://hdl.handle.net/"]:
            if normalized.lower().startswith(prefix.lower()):
                normalized = normalized[len(prefix) :]
                break

        self._handle = normalized
        error_message = self._validate()
        if error_message:
            raise InvalidHandle(error_message)

    @staticmethod
    def type() -> str:
        return "Handle"

    def _validate(self) -> str | None:
        """Validate Handle format: must contain prefix/suffix."""
        if "/" not in self._handle:
            return "Invalid Handle format: must contain '/'"

        parts = self._handle.split("/")
        if len(parts) != 2:
            return "Invalid Handle format: must contain exactly one '/'"

        prefix, suffix = parts
        if not prefix or not suffix:
            return "Invalid Handle format: both prefix and suffix must be non-empty"

        return None

    def value(self) -> str:
        return self._handle

    def url(self) -> str:
        return f"https://hdl.handle.net/{self}"

    def __str__(self) -> str:
        return self._handle

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Handle):
            return False
        return self._handle == other._handle

    def __hash__(self) -> int:
        return hash((self._handle,))


class InvalidUrn(DomainError):
    def __init__(self, message: str = "Invalid URN format", *args: object) -> None:
        super().__init__(message, *args)


class Urn:
    """Uniform Resource Name (URN) validation.

    Format: urn:namespace:specific-string (e.g., urn:isbn:0451450523)
    According to RFC 8141
    """

    __match_args__ = ("_urn",)

    def __init__(self, urn: str) -> None:
        # Normalize to lowercase per RFC 8141 (URN scheme and namespace are case-insensitive)
        normalized = NonEmptyStr(urn).strip().lower()
        self._urn = normalized
        error_message = self._validate()
        if error_message:
            raise InvalidUrn(error_message)

    @staticmethod
    def type() -> str:
        return "URN"

    def _validate(self) -> str | None:
        """Validate URN format: must be urn:namespace:specific-string."""
        if not self._urn.startswith("urn:"):
            return "Invalid URN format: must start with 'urn:'"

        parts = self._urn.split(":", 2)  # Split into at most 3 parts
        if len(parts) < 3:
            return "Invalid URN format: must be 'urn:namespace:specific-string'"

        _, namespace, specific = parts
        if not namespace:
            return "Invalid URN format: namespace cannot be empty"

        if not specific:
            return "Invalid URN format: specific string cannot be empty"

        return None

    def value(self) -> str:
        return self._urn

    def url(self) -> str | None:
        return None

    def __str__(self) -> str:
        return self._urn

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Urn):
            return False
        return self._urn == other._urn

    def __hash__(self) -> int:
        return hash((self._urn,))


class InvalidArxiv(DomainError):
    def __init__(self, message: str = "Invalid arXiv format", *args: object) -> None:
        super().__init__(message, *args)


class InvalidOai(DomainError):
    def __init__(self, message: str = "Invalid OAI format", *args: object) -> None:
        super().__init__(message, *args)


class Arxiv:
    """arXiv identifier validation.

    Supports three formats:
    - Old format (pre-2007): archive/YYMMNNN (e.g., hep-th/9901001)
    - 2007-2014 format: YYMM.NNNN (e.g., 0704.0001)
    - Current format (2015+): YYMM.NNNNN (e.g., 1501.00001)
    - Optional arXiv: prefix (e.g., arXiv:1501.00001)
    - Optional version suffix: v1, v2, etc.
    """

    __match_args__ = ("_arxiv",)

    def __init__(self, arxiv: str) -> None:
        normalized = NonEmptyStr(arxiv).strip()

        # Normalize arXiv: prefix to proper case if present
        if normalized.lower().startswith("arxiv:"):
            normalized = "arXiv:" + normalized[6:]  # Normalize prefix to arXiv:
        elif ":" not in normalized:
            # Add prefix if not present (for plain identifiers)
            normalized = "arXiv:" + normalized

        self._arxiv = normalized
        error_message = self._validate()
        if error_message:
            raise InvalidArxiv(error_message)

    @staticmethod
    def type() -> str:
        return "arXiv"

    def _validate(self) -> str | None:
        if not self._arxiv.startswith("arXiv:"):
            return "Invalid arXiv format: must start with 'arXiv:'"

        # Extract the part after arXiv:
        identifier = self._arxiv[6:]

        # Old format: archive/YYMMNNN[vN]
        old_format = r"^[a-z]+-?[a-z]+/\d{7}(v\d+)?$"

        # New format (2007-2014): YYMM.NNNN[vN]
        mid_format = r"^\d{4}\.\d{4}(v\d+)?$"

        # Current format (2015+): YYMM.NNNNN[vN]
        new_format = r"^\d{4}\.\d{5}(v\d+)?$"

        if any(
            re.match(pattern, identifier, re.IGNORECASE)
            for pattern in [old_format, mid_format, new_format]
        ):
            return None

        return (
            "Invalid arXiv format: must be arXiv:archive/YYMMNNN, arXiv:YYMM.NNNN, "
            "or arXiv:YYMM.NNNNN (optionally with version suffix vN)"
        )

    def value(self) -> str:
        return self._arxiv

    def url(self) -> str:
        return f"https://arxiv.org/abs/{self}"

    def __str__(self) -> str:
        return self._arxiv

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Arxiv):
            return False
        return self._arxiv == other._arxiv

    def __hash__(self) -> int:
        return hash((self._arxiv,))


class Oai:
    """OAI (Open Archives Initiative) identifier validation.

    Format: oai:namespace-identifier:local-identifier
    According to OAI-PMH v2.0 specification
    Example: oai:arXiv.org:hep-th/9901001
    """

    __match_args__ = ("_oai",)

    def __init__(self, oai: str) -> None:
        self._oai = NonEmptyStr(oai).strip()
        error_message = self._validate()
        if error_message:
            raise InvalidOai(error_message)

    @staticmethod
    def type() -> str:
        return "OAI"

    def _validate(self) -> str | None:
        """Validate OAI format: oai:namespace-identifier:local-identifier."""
        if not self._oai.startswith("oai:"):
            return "Invalid OAI format: must start with 'oai:'"

        # Split into scheme, namespace, and local parts
        parts = self._oai.split(":", 2)  # Split into at most 3 parts
        if len(parts) < 3:
            return "Invalid OAI format: must be 'oai:namespace-identifier:local-identifier'"

        scheme, namespace, local_id = parts

        if not namespace:
            return "Invalid OAI format: namespace-identifier cannot be empty"

        if not local_id:
            return "Invalid OAI format: local-identifier cannot be empty"

        # Check for unescaped spaces in local identifier
        if " " in local_id:
            return "Invalid OAI format: spaces must be percent-encoded as %20"

        # Validate namespace is a domain name (must contain at least one dot and start with letter)
        if "." not in namespace:
            return "Invalid OAI format: namespace-identifier must be a domain name (contain '.')"

        # Check that namespace starts with a letter (domain name requirement)
        if not namespace[0].isalpha():
            return "Invalid OAI format: namespace-identifier must start with a letter"

        return None

    def value(self) -> str:
        return self._oai

    def url(self) -> str | None:
        return None

    def __str__(self) -> str:
        return self._oai

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Oai):
            return False
        return self._oai == other._oai

    def __hash__(self) -> int:
        return hash((self._oai,))


_LinkTypes = {t.type(): t for t in (Doi, Isbn, Url, Pmid, Pmc, Handle, Urn, Arxiv, Oai)}
_LoweredLinkTypes = {t_name.lower(): t for t_name, t in _LinkTypes.items()}


def link_types() -> list[str]:
    return list(_LinkTypes.keys())


def valid_link_type(v: str) -> bool:
    return v.lower() in _LoweredLinkTypes


def create_link(link_type: str, link_value: str) -> Link:
    link_constructor = _LoweredLinkTypes.get(link_type.lower())
    if not link_constructor:
        return UserLink(link_type=link_type, link_value=link_value)

    return link_constructor(link_value)
