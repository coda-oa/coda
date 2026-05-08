from collections.abc import Iterable
from coda.domain.author import Author
from coda.domain.errors import DomainError
from coda.domain.publication.links import Doi
from coda.domain.publication.publication import PublicationId


class InvalidMetadataError(DomainError):
    """Raised when DOI metadata is invalid or missing required fields."""


class DOIAlreadyImported(DomainError):
    """Raised when attempting to import a DOI that already exists in the database."""

    def __init__(
        self,
        doi: Doi,
        existing_publication_id: PublicationId,
        existing_publication_title: str,
        existing_publication_authors: Iterable[Author],
    ) -> None:
        self.doi = doi
        self.publication_id = existing_publication_id
        self.publication_title = existing_publication_title
        self.publication_authors = existing_publication_authors
        super().__init__(
            "\n".join(
                (
                    f"DOI {doi} already exists in database.",
                    f"Title: {existing_publication_title}",
                    f"Authors: {', '.join(a.name for a in existing_publication_authors)}",
                )
            )
        )
