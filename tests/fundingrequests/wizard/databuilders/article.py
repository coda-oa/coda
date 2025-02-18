from typing import Self

from coda.apps.publications.dto import PublicationDto
from coda.publication import JournalId, Publication, PublicationId
from tests import domainfactory, modelfactory
from tests.fundingrequests.wizard.databuilders._base import FundingRequestDataBuilder


class ArticleRequestDataBuilder(FundingRequestDataBuilder[Publication]):
    def __init__(self) -> None:
        super().__init__()
        self.journal = modelfactory.journal()
        self._publication = self.create_publication(JournalId(self.journal.pk))

    def create_publication(
        self, journal: JournalId, *, id: PublicationId | None = None
    ) -> Publication:
        return domainfactory.publication(
            journal=journal,
            publication_type=list(self.publication_types.concepts)[0],
            subject_area=list(self.subject_areas.concepts)[0],
            contracts=tuple(self.contract_years),
            id=id,
        )

    def with_new_publication(self, id: PublicationId | None = None) -> Self:
        self.journal = modelfactory.journal()
        self._publication = self.create_publication(JournalId(self.journal.pk), id=id)
        return self

    def with_journal(self, journal: JournalId) -> Self:
        self._publication.journal = journal
        return self

    @property
    def publication(self) -> Publication:
        return self._publication

    def publication_dto(self) -> PublicationDto:
        return PublicationDto.from_publication(self._publication)
