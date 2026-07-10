import httpx
from coda.domain.errors import DomainError
from coda.domain.publication.links import Doi


class DOINotFoundError(DomainError):
    """Raised when a DOI is not found in external metadata sources."""

    def __init__(self, doi: Doi, *args: object) -> None:
        super().__init__(f"DOI not found: {doi}", *args)
        self.doi = doi


class DOIFetchError(DomainError):
    """Raised when DOI fetch fails due to network/API errors.

    This is distinct from DOINotFoundError (404) - this represents
    infrastructure failures like timeouts, network errors, server errors.
    """

    def __init__(self, doi: Doi, reason: str, *args: object) -> None:
        super().__init__(f"Failed to fetch DOI {doi}: {reason}", *args)
        self.doi = doi
        self.reason = reason


def map_to_doi_error(err: Exception, doi: Doi) -> DOINotFoundError | DOIFetchError:
    match err:
        case httpx.TimeoutException() as e:
            return DOIFetchError(doi, "Request timeout")
        case httpx.ConnectError() as e:
            return DOIFetchError(doi, "Network connection failed")
        case httpx.HTTPStatusError() as e:
            if e.response.status_code == 404:
                return DOINotFoundError(doi)
            status = e.response.status_code
            if status == 429:
                return DOIFetchError(doi, "Rate limit exceeded (429)")
            elif 500 <= status < 600:
                return DOIFetchError(doi, f"Server error ({status})")
            else:
                return DOIFetchError(doi, f"HTTP error ({status})")
        case httpx.HTTPError() as e:
            return DOIFetchError(doi, f"Network error: {type(e).__name__}")
        case _:
            return DOIFetchError(doi, "Invalid JSON response from API")
