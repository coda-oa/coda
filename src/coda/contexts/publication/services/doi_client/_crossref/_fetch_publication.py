import datetime
from typing import Any

import httpx

from coda.contexts.publication.dto.external_metadata import (
    ExternalAuthor,
    ExternalFundingMetadata,
    ExternalFundingOrganisationMetadata,
    ExternalJournal,
    ExternalPublicationMetadata,
)
from coda.contexts.publication.services.doi_client.errors import map_to_doi_error
from coda.domain.publication.links import Doi

CROSSREF_API_BASE = "https://api.crossref.org/works/"


def fetch_publication(doi: Doi, timeout: int = 10) -> ExternalPublicationMetadata:
    """Fetch metadata from Crossref API.

    Raises:
        DOINotFoundError: If DOI not found (404)
        DOIFetchError: If request fails due to network/API errors
    """
    url = f"{CROSSREF_API_BASE}{doi}"

    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True).raise_for_status()
        data = response.json()

        return _parse_crossref_response(data)
    except Exception as e:
        raise map_to_doi_error(e, doi) from e


def _parse_crossref_response(data: dict[str, Any]) -> ExternalPublicationMetadata:
    """Parse Crossref JSON response into our metadata structure."""
    message = data.get("message", {})

    titles = message.get("title", [])
    title = titles[0] if titles else "Untitled"
    authors = _parse_authors(message.get("author", []))
    pub_type = message.get("type", "unknown")
    journal = _parse_journal(message) if pub_type == "journal-article" else None
    publisher = message.get("publisher")
    isbn = _extract_isbn(message)

    license_info = _parse_license(message.get("license", []))

    online_date = _parse_date(message.get("published-online"))
    print_date = _parse_date(message.get("published-print"))

    funders_data = message.get("funder", [])
    funders = [_parse_funder(f) for f in funders_data]
    funders = [f for f in funders if f is not None]

    return ExternalPublicationMetadata(
        title=title,
        authors=authors,
        publication_type=pub_type,
        journal=journal,
        publisher=publisher,
        isbn=isbn,
        license=license_info,
        online_publication_date=online_date,
        print_publication_date=print_date,
        funders=funders,
    )


def _parse_authors(author_data: list[dict[str, Any]]) -> list[ExternalAuthor]:
    """Parse author list from Crossref format."""
    return [_parse_author(author) for author in author_data]


def _parse_author(author: dict[str, Any]) -> ExternalAuthor:
    """Parse a single author from Crossref format."""
    name = _extract_author_name(author)
    affiliation_name, ror_id = _extract_affiliation_info(author)

    return ExternalAuthor(
        name=name,
        affiliation=affiliation_name,
        orcid=author.get("ORCID"),
    )


def _extract_author_name(author: dict[str, Any]) -> str:
    """Extract author name from Crossref author object."""
    given = author.get("given", "")
    family = author.get("family", "")
    return f"{given} {family}".strip() if given or family else "Unknown Author"


def _extract_affiliation_info(author: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract affiliation name and ROR ID from Crossref author object."""
    affiliations = author.get("affiliation", [])
    if not affiliations:
        return None, None

    first_affil = affiliations[0]
    affiliation_name = first_affil.get("name")
    ror_id = _extract_ror_id(first_affil)

    return affiliation_name, ror_id


def _extract_ror_id(affiliation: dict[str, Any]) -> str | None:
    """Extract ROR ID from affiliation object."""
    affil_ids = affiliation.get("id", [])
    for aid in affil_ids:
        if aid.get("id-type") == "ROR":
            ror_id = aid.get("id")
            return str(ror_id) if ror_id else None
    return None


def _parse_journal(message: dict[str, Any]) -> ExternalJournal | None:
    """Parse journal information from Crossref response."""
    title = _extract_journal_title(message)
    if title is None:
        return None

    issn, eissn = _extract_issns(message)
    return ExternalJournal(title=title, issn=issn, eissn=eissn)


def _extract_journal_title(message: dict[str, Any]) -> str | None:
    """Extract journal title from Crossref response."""
    container_titles = message.get("container-title", [])
    return container_titles[0] if container_titles else None


def _extract_issns(message: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract print and electronic ISSNs from Crossref response."""
    issns = message.get("ISSN", [])
    issn_types = message.get("issn-type", [])

    issn = None
    eissn = None

    for issn_data in issn_types:
        issn_value = issn_data.get("value")
        issn_type = issn_data.get("type")

        if issn_type == "print":
            issn = issn_value
        elif issn_type == "electronic":
            eissn = issn_value

    if not issn and not eissn and issns:
        issn = issns[0] if len(issns) > 0 else None
        eissn = issns[1] if len(issns) > 1 else None

    return issn, eissn


def _extract_isbn(message: dict[str, Any]) -> str | None:
    """Extract ISBN from Crossref response.

    Crossref provides ISBN as an array. We return the first one if available.
    """
    isbns = message.get("ISBN", [])
    return isbns[0] if isbns else None


def _parse_license(license_data: list[dict[str, Any]]) -> str | None:
    """Parse license information from Crossref response."""
    if not license_data:
        return None

    first_license = license_data[0]
    url = first_license.get("URL", "")

    if "creativecommons.org/licenses/" in url:
        return _extract_creative_commons_license(url)

    return url if url else None


def _extract_creative_commons_license(url: str) -> str:
    """Extract Creative Commons license identifier from a creativecommons.org URL.

    Crossref license URLs follow the pattern:
        https://creativecommons.org/licenses/<type>/<version>/
    e.g. https://creativecommons.org/licenses/by/4.0/ → "CC-BY"

    The second-to-last path segment is the license type slug (e.g. "by", "by-nc").
    We upper-case it and prepend "CC-" to produce the canonical identifier.
    If the URL does not have enough path segments to extract a type, we return
    the raw URL unchanged so the caller can fall back to License.Unknown.
    """
    parts = url.rstrip("/").split("/")
    # Need at least: ['https:', '', 'creativecommons.org', 'licenses', '<type>', '<version>']
    if len(parts) < 2:
        return url

    license_type = parts[-2].upper()  # e.g. "BY", "BY-NC-ND"
    return f"CC-{license_type}"


def _parse_date(date_data: dict[str, Any] | None) -> datetime.date | None:
    """Parse date from Crossref format (date-parts array)."""
    if not date_data:
        return None

    date_parts = date_data.get("date-parts", [[]])[0]
    if not date_parts:
        return None

    year = date_parts[0] if len(date_parts) > 0 else None
    if not year:
        return None

    month = date_parts[1] if len(date_parts) > 1 else 1
    day = date_parts[2] if len(date_parts) > 2 else 1

    try:
        return datetime.date(year, month, day)
    except ValueError:
        return datetime.date(year, 1, 1)


def _parse_funder(funder_data: dict[str, Any] | None) -> ExternalFundingMetadata | None:
    if funder_data is None:
        return None

    if "name" not in funder_data and "DOI" not in funder_data:
        return None

    doi = funder_data.get("DOI")
    identifiers = [doi] if doi else []

    funder = ExternalFundingOrganisationMetadata(name=funder_data["name"], identifiers=identifiers)

    award_list = funder_data.get("award", [])
    award = award_list[0] if award_list else ""
    return ExternalFundingMetadata(funder=funder, project_id=award)
