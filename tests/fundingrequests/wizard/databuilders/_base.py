import abc
import datetime
import random
from collections.abc import Iterable
from typing import Generic, Self, TypeVar
from unittest.mock import create_autospec

from faker import Faker

from coda.apps.contracts.repository import as_domain_object
from coda.apps.fundingrequests.dto import (
    ExternalFundingDto,
    ExtraContactDto,
    ExtraInformationDto,
    PaymentDto,
)
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.publications.dto import MonographDto, PublicationDto
from coda.apps.publications.repositories import vocabulary_repository
from coda.domain.contract import ContractYear
from coda.domain.fundingrequest import (
    ExternalFunding,
    FilledContact,
    FundingOrganizationId,
    FundingRequest,
    FundingRequestContact,
    NoContact,
    Payment,
    TPublication,
)
from coda.domain.fundingrequest.identity import PublicFundingRequestId
from coda.domain.publication import PublicationId
from coda.domain.string import NonEmptyStr
from tests import domainfactory, modelfactory


def fixed_request_id_factory(
    date: datetime.date | None = None, rng: random.Random | None = None
) -> PublicFundingRequestId:
    date = datetime.date.today()
    rng_ = create_autospec(random.Random)
    rng_.randint.return_value = 1
    return PublicFundingRequestId.create(date, rng_)


TPublicationDto = TypeVar("TPublicationDto", PublicationDto, MonographDto)


class FundingRequestDataBuilder(Generic[TPublication, TPublicationDto], abc.ABC):
    def __init__(self) -> None:
        self._faker = Faker()
        self.affiliation = modelfactory.institution()
        self.funder = modelfactory.funding_organization()
        self.contracts = [as_domain_object(modelfactory.contract()) for _ in range(1, 3)]
        self.contract_years = [domainfactory.contract_year(c) for c in self.contracts]

        self.extra_contact: FundingRequestContact = FilledContact(
            name=NonEmptyStr(self._faker.name()), email=self._faker.email()
        )
        self.estimated_cost = domainfactory.payment()
        self.external_funding = [
            domainfactory.external_funding(FundingOrganizationId(self.funder.pk)),
            domainfactory.external_funding(FundingOrganizationId(self.funder.pk)),
        ]
        self._request_remarks = self._faker.sentence()

        self.prepare_vocabularies()
        self.set_global_preferences()

    def without_external_funding(self) -> Self:
        self.external_funding = []
        return self

    def with_empty_contact(self) -> Self:
        self.extra_contact = NoContact
        return self

    def with_new_contact(self) -> Self:
        self.extra_contact = domainfactory.fundingrequest_contact()
        return self

    def with_new_request_remarks(self) -> Self:
        self._request_remarks = self._faker.sentence()
        return self

    def with_contracts(self, contract_years: Iterable[ContractYear]) -> Self:
        self.contracts = [c.contract for c in contract_years]
        self.contract_years = list(contract_years)
        self.publication.contracts = tuple(self.contract_years)
        return self

    def prepare_vocabularies(self) -> None:
        self.subject_areas = vocabulary_repository.create("subject_areas", "1.0")
        self.subject_areas.add_concept("subject_area", "subject_area")
        vocabulary_repository.save(self.subject_areas)

        self.publication_types = vocabulary_repository.create("publication_types", "1.0")
        self.publication_types.add_concept("publication_type", "publication_type")
        vocabulary_repository.save(self.publication_types)

    def set_global_preferences(self) -> None:
        GlobalPreferences.set_subject_classification_vocabulary(self.subject_areas)
        GlobalPreferences.set_article_publication_type_vocabulary(self.publication_types)

    @abc.abstractmethod
    def publication_dto(self) -> TPublicationDto:
        ...

    @property
    @abc.abstractmethod
    def publication(self) -> TPublication:
        ...

    def build(self) -> FundingRequest[TPublication]:
        return FundingRequest.new(
            self.publication,
            self.estimated_cost,
            request_id=fixed_request_id_factory(),
            external_funding=self.external_funding,
            extra_contact=self.extra_contact,
            request_remarks=self._request_remarks,
        )

    @property
    def expected(self) -> FundingRequest[TPublication]:
        return self.build()

    @abc.abstractmethod
    def with_new_publication(self, id: PublicationId | None = None) -> Self:
        ...

    def with_payment(self, payment: Payment) -> Self:
        self.estimated_cost = payment
        return self

    def extra_information_dto(self) -> ExtraInformationDto:
        return ExtraInformationDto(
            extra_contact=ExtraContactDto.from_contact(self.extra_contact),
            request_remarks=self._request_remarks,
        )

    def external_funding_dto(self) -> list[ExternalFundingDto]:
        return [self._to_external_funding_dto(f) for f in self.external_funding]

    def cost_dto(self) -> PaymentDto:
        return PaymentDto.from_payment(self.estimated_cost)

    def _to_external_funding_dto(self, funding: ExternalFunding) -> ExternalFundingDto:
        return ExternalFundingDto.from_external_funding(funding)
