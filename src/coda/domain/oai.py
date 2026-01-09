from typing import Any

from coda.domain.errors import DomainError
from coda.domain.string import NonEmptyStr


class InvalidOai(DomainError):
    def __init__(self, message: str = "Invalid OAI format", *args: object) -> None:
        super().__init__(message, *args)


class Oai:
    """OAI (Open Archives Initiative) identifier validation.

    Format: oai:namespace-identifier:local-identifier
    According to OAI-PMH v2.0 specification (https://www.openarchives.org/OAI/2.0/guidelines-oai-identifier.htm)
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

        _, namespace, local_id = parts

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
