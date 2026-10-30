"""Crossref polite-pool credentials and their HTTP representation.

Politeness tiers (https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/):

- Public: no identification. 5 requests/s, 1 concurrent request.
- Polite: contact email in the ``mailto`` query parameter or the
  ``User-Agent`` header. 10 requests/s, 3 concurrent requests.
- Metadata Plus: API key in the ``Crossref-Plus-API-Token`` header.
  150 requests/s, no concurrency limit.

The email goes into *both* the query param and the User-Agent: either alone
qualifies for the polite pool, but intermediaries can rewrite headers, and
losing pool membership is silent. The Plus token is sent as
``Crossref-Plus-API-Token: Bearer <key>`` as documented for Metadata Plus.
"""

from dataclasses import dataclass

from coda.domain.string import NonEmptyStr


@dataclass(frozen=True, slots=True)
class CrossrefPoliteness:
    """Credentials identifying this instance to the Crossref REST API."""

    email: NonEmptyStr | None = None
    plus_token: str | None = None

    def __post_init__(self) -> None:
        if self.plus_token is not None and not self.plus_token.strip():
            raise ValueError("Plus token must not be blank")
        if self.email is not None and not self.email.strip():
            raise ValueError("Email must not be blank")

    @property
    def is_plus(self) -> bool:
        return self.plus_token is not None

    def query_params(self) -> dict[str, str]:
        """Query parameters identifying the caller to Crossref."""
        if self.email is None:
            return {}
        return {"mailto": str(self.email)}

    def headers(self) -> dict[str, str]:
        """Request headers identifying the caller to Crossref."""
        headers: dict[str, str] = {}
        if self.email is not None:
            headers["User-Agent"] = self._user_agent()
        if self.plus_token is not None:
            headers["Crossref-Plus-API-Token"] = f"Bearer {self.plus_token}"
        return headers

    def _user_agent(self) -> str:
        import importlib.metadata

        try:
            version = importlib.metadata.version("coda")
        except importlib.metadata.PackageNotFoundError:
            version = "dev"

        return f"coda/{version} (mailto:{self.email})"
