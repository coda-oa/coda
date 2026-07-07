"""Immediate (eager) implementation of the DOIRepository protocol.

Each method call performs its database operation immediately. This is the
default repository used by DOIImportService for single-DOI imports.
"""

from __future__ import annotations

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


class BaseImmediateDOIRepository:
    def __init__(self, funder_resolver: FunderResolver | None = None) -> None:
        self._funder_resolver = funder_resolver or DatabaseFunderResolver()

    def find_publication_by_doi(self, doi: Doi) -> BasePublication | None:
        return publication_repository.find_by_doi(doi)

    def find_journal_by_eissn(self, issn: Issn) -> Journal | None:
        return journal_services.find_by_eissn(issn)

    def create_journal(
        self, title: NonEmptyStr, eissn: Issn, publisher_id: PublisherId
    ) -> JournalId:
        return journal_services.create(title=title, eissn=eissn, publisher_id=publisher_id)

    def find_publisher_by_name(self, name: str) -> Publisher | None:
        return publisher_services.find_by_name(name)

    def get_publisher_by_id(self, publisher_id: PublisherId) -> Publisher:
        return publisher_services.get_by_pk(publisher_id)

    def create_publisher(self, name: str) -> PublisherId:
        return publisher_services.create(name=name)

    def get_journal_by_id(self, journal_id: JournalId) -> Journal:
        return journal_services.get_by_pk(journal_id)

    def get_funding_org_names(
        self, ids: list[FundingOrganizationId]
    ) -> dict[FundingOrganizationId, str]:
        orgs = funding_repository.get_funding_organizations_by_ids(list(ids))
        return {FundingOrganizationId(org.pk): org.name for org in orgs}

    def create_funding_request(
        self,
        preview: PreviewFundingRequest,
        override: OverrideImport,
        funder_matches: list[FunderMatch],
    ) -> FundingRequestId:
        dto = build_creation_dto(self, self._funder_resolver, preview, override, funder_matches)
        return fundingrequests.create_fundingrequest(dto, checkfactory=NullCheckFactory())


class ImmediateDOIRepository(BaseImmediateDOIRepository):
    """DOIRepository that performs all DB operations immediately.

    Wraps existing service/repository calls directly with no batching
    or deferral. Suitable for single-DOI imports.
    """

    pass
