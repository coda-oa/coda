# Re-export InMemoryDOIMetadataClient for backwards compatibility with existing test imports.
# New tests should import directly from coda.contexts.publication.services.fakes.
from coda.contexts.publication.services.fakes import (
    InMemoryDOIMetadataClient as FakeDOIMetadataClient,
)

__all__ = ["FakeDOIMetadataClient"]
