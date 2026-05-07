"""Import-scoped publication lookup repository.

Prefetches FundingRequest→Publication mappings in one query so that
parse_into_position can resolve request IDs to PublicationIds without
hitting the database per position.
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db.models import Q

from coda.apps.fundingrequests.models import FundingRequest
from coda.domain.publication.publication import PublicationId

if TYPE_CHECKING:
    from coda.contexts.finance.dto.import_dtos import InvoiceImportDto


class PublicationImportRepository:
    def __init__(self) -> None:
        self._cache: dict[str, PublicationId] = {}

    def prefetch(self, invoice_dtos: "Iterable[InvoiceImportDto]") -> None:
        """Bulk load request_id → PublicationId mappings (one query)."""
        from coda.contexts.finance.dto.import_dtos import PublicationPositionImportDto

        request_ids = {
            str(position.request_id or position.legacy_request_id)
            for invoice_dto in invoice_dtos
            for position in invoice_dto.positions
            if isinstance(position, PublicationPositionImportDto)
            and (position.request_id or position.legacy_request_id)
        }

        if not request_ids:
            return

        requests = FundingRequest.objects.filter(
            Q(request_id__in=request_ids) | Q(legacy_request_id__in=request_ids)
        ).prefetch_related("publication")

        for req in requests:
            pub_id = PublicationId(req.publication.id)
            self._cache[req.request_id] = pub_id
            if req.legacy_request_id:
                self._cache[req.legacy_request_id] = pub_id

    def get(self, request_id: str) -> PublicationId:
        """Return the PublicationId for a request ID.

        Raises:
            KeyError: if the request_id was not found during prefetch.
        """
        return self._cache[request_id]
