from typing import Self

from coda.apps.fundingrequests.views.wizard.steps.publisher_step import PublisherStepDto
from coda.apps.publications.dto import MonographDto
from coda.domain.contract import PublisherId
from coda.domain.publication import Monograph, PublicationId
from tests import domainfactory, modelfactory
from tests.fundingrequests.wizard.databuilders._base import FundingRequestDataBuilder


class MonographRequestDataBuilder(FundingRequestDataBuilder[Monograph, MonographDto]):
    def __init__(self) -> None:
        super().__init__()
        publisher = modelfactory.publisher()
        self._publication = self.create_monograph(PublisherId(publisher.pk))

    def create_monograph(
        self, publisher: PublisherId, id: PublicationId | None = None
    ) -> Monograph:
        return domainfactory.monograph(
            publisher=publisher,
            publication_type=list(self.publication_types.concepts)[0],
            subject_area=list(self.subject_areas.concepts)[0],
            contracts=tuple(self.contract_years),
            id=id,
        )

    def with_new_publication(self, id: PublicationId | None = None) -> Self:
        publisher = modelfactory.publisher()
        self._publication = self.create_monograph(PublisherId(publisher.pk), id)
        return self

    def with_publisher(self, publisher: PublisherId) -> Self:
        self.publication.publisher = publisher
        return self

    @property
    def publication(self) -> Monograph:
        return self._publication

    def publication_dto(self) -> MonographDto:
        return MonographDto.from_monograph(self.publication)

    def publisher_step_dto(self) -> PublisherStepDto:
        return PublisherStepDto.from_monograph(self.publication)
