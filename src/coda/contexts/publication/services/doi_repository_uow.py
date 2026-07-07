"""Unit-of-Work implementation of the DOIRepository protocol.

Collects all database operations in memory during the import loop and
flushes them in bulk when ``commit()`` is called. Read operations use
local caches to avoid N+1 lookups.

Write operations store raw metadata drafts (no DB IDs) until
``commit()`` resolves journals, publishers, and funders in bulk and
persists all funding requests via ``bulk_create_fundingrequests``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coda.apps.fundingrequests import repository as funding_repository
from coda.apps.journals import services as journal_services
from coda.apps.publications.repositories import publication_repository
from coda.apps.publishers import services as publisher_services
from coda.checks.nullcheckfactory import NullCheckFactory
from coda.contexts.fundingrequest.services import fundingrequests
from coda.contexts.fundingrequest.services.funder_resolver import FunderMatch
from coda.contexts.publication.dto.preview import PreviewFundingRequest
from coda.contexts.publication.services._dto_builder import build_creation_dto
from coda.contexts.publication.services.doi_import_service import (
    DatabaseFunderResolver,
    FunderResolver,
    OverrideImport,
)
from coda.domain.contract import PublisherId
from coda.domain.fundingrequest import FundingRequestId
from coda.domain.fundingrequest.fundingrequest import FundingOrganizationId
from coda.domain.issn import Issn
from coda.domain.publication import JournalId
from coda.domain.publication.links import Doi
from coda.domain.publication.publication import BasePublication
from coda.domain.string import NonEmptyStr

if TYPE_CHECKING:
    from coda.apps.journals.models import Journal
    from coda.apps.publishers.models import Publisher


@dataclass
class _DraftImport:
    preview: PreviewFundingRequest
    override: OverrideImport
    funder_matches: list[FunderMatch] = field(default_factory=list)


class _PreResolvedFunderResolver:
    """FunderResolver that returns a pre-computed map for all matches.

    Created by ``UnitOfWorkDOIRepository.commit()`` after resolving all
    funders once, so each per-draft ``build_creation_dto`` call reuses
    the batch-resolved map without additional DB lookups.
    """

    def __init__(self, funder_map: dict[str, FundingOrganizationId]) -> None:
        self._funder_map = funder_map

    def resolve(self, matches: list[FunderMatch]) -> dict[str, FundingOrganizationId]:
        return self._funder_map


class UnitOfWorkDOIRepository:
    """DOIRepository that defers writes and flushes in bulk on ``commit()``.

    Read methods cache results for the lifetime of the unit of work.

    ``create_funding_request`` stores a draft.  ``commit()`` resolves
    journals, publishers, and funders for all drafts in a single batch
    sequence, builds the ``CreateFundingRequestDto`` objects, and bulk-
    creates the funding requests.

    Usage::

        uow = UnitOfWorkDOIRepository()
        service = DOIImportService(doi_client, repo=uow)
        for doi, override in pairs:
            service.import_from_doi(doi, override)
        results = uow.commit()
    """

    def __init__(self, funder_resolver: FunderResolver | None = None) -> None:
        self._doi_cache: dict[str, BasePublication | None] = {}
        self._journal_eissn_cache: dict[str, Journal | None] = {}
        self._journal_id_cache: dict[JournalId, Journal | None] = {}
        self._publisher_name_cache: dict[str, Publisher | None] = {}
        self._publisher_id_cache: dict[PublisherId, Publisher | None] = {}
        self._drafts: list[_DraftImport] = []
        self._funder_resolver = funder_resolver or DatabaseFunderResolver()

    # ------------------------------------------------------------------
    # Batch pre-warm (call before per-DOI loop to avoid N+1 duplicate checks)
    # ------------------------------------------------------------------

    def prewarm_doi_cache(self, dois: list[Doi]) -> None:
        if not dois:
            return
        existing = publication_repository.find_by_dois(dois)
        for key, pub in existing.items():
            self._doi_cache[key] = pub
        for doi in dois:
            key = str(doi)
            if key not in self._doi_cache:
                self._doi_cache[key] = None

    # ------------------------------------------------------------------
    # Read helpers (cached)
    # ------------------------------------------------------------------

    def find_publication_by_doi(self, doi: Doi) -> BasePublication | None:
        key = str(doi)
        if key not in self._doi_cache:
            self._doi_cache[key] = publication_repository.find_by_doi(doi)
        return self._doi_cache[key]

    def find_journal_by_eissn(self, issn: Issn) -> Journal | None:
        key = str(issn)
        if key not in self._journal_eissn_cache:
            self._journal_eissn_cache[key] = journal_services.find_by_eissn(issn)
        return self._journal_eissn_cache[key]

    def find_publisher_by_name(self, name: str) -> Publisher | None:
        if name not in self._publisher_name_cache:
            self._publisher_name_cache[name] = publisher_services.find_by_name(name)
        return self._publisher_name_cache[name]

    def get_journal_by_id(self, journal_id: JournalId) -> Journal:
        if journal_id not in self._journal_id_cache:
            self._journal_id_cache[journal_id] = journal_services.get_by_pk(journal_id)
        result = self._journal_id_cache[journal_id]
        if result is None:
            raise LookupError(f"Journal not found: {journal_id}")
        return result

    def get_publisher_by_id(self, publisher_id: PublisherId) -> Publisher:
        if publisher_id not in self._publisher_id_cache:
            self._publisher_id_cache[publisher_id] = publisher_services.get_by_pk(publisher_id)
        result = self._publisher_id_cache[publisher_id]
        if result is None:
            raise LookupError(f"Publisher not found: {publisher_id}")
        return result

    def get_funding_org_names(
        self, ids: list[FundingOrganizationId]
    ) -> dict[FundingOrganizationId, str]:
        orgs = funding_repository.get_funding_organizations_by_ids(list(ids))
        return {FundingOrganizationId(org.pk): org.name for org in orgs}

    def create_journal(
        self, title: NonEmptyStr, eissn: Issn, publisher_id: PublisherId
    ) -> JournalId:
        return journal_services.create(title=title, eissn=eissn, publisher_id=publisher_id)

    def create_publisher(self, name: str) -> PublisherId:
        return publisher_services.create(name=name)

    def create_funding_request(
        self,
        preview: PreviewFundingRequest,
        override: OverrideImport,
        funder_matches: list[FunderMatch],
    ) -> FundingRequestId:
        self._drafts.append(
            _DraftImport(preview=preview, override=override, funder_matches=funder_matches)
        )
        return FundingRequestId(len(self._drafts))

    def commit(self) -> list[FundingRequestId]:
        """Resolve all drafts and bulk-create funding requests in one pass.

        1. Collect all funder matches across drafts and resolve once.
        2. For each draft, build a ``CreateFundingRequestDto`` using the
           ``build_creation_dto`` helper with pre-resolved funders.
        3. Bulk-create all funding requests.
        """
        if not self._drafts:
            return []

        # Step 1: resolve all funders once
        all_matches: list[FunderMatch] = []
        for draft in self._drafts:
            all_matches.extend(draft.funder_matches)

        funder_map: dict[str, FundingOrganizationId] = {}
        if all_matches:
            funder_map = self._funder_resolver.resolve(all_matches)

        # Step 2: build DTOs for each draft (all reuse the batch-resolved funder map)
        batch_resolver = _PreResolvedFunderResolver(funder_map)
        dtos = []
        for draft in self._drafts:
            dto = build_creation_dto(
                self,
                batch_resolver,
                draft.preview,
                draft.override,
                draft.funder_matches,
            )
            dtos.append(dto)

        # Step 3: bulk-create
        fr_ids, _ = fundingrequests.bulk_create_fundingrequests(
            dtos,
            checkfactory=NullCheckFactory(),
        )
        return list(fr_ids)
