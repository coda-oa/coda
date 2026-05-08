from django.db.models import Prefetch, QuerySet

from coda.apps.authors.mappers._domain import AuthorDomainMapper
from coda.apps.authors.models import Author as AuthorModel
from coda.apps.contracts.mappers import ContractDomainMapper
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel, Label
from coda.apps.fundingrequests.queries.mappers import PaymentDetailMapper
from coda.apps.fundingrequests.queries.models import FundingRequestListItem
from coda.domain.contract import ContractYear
from coda.domain.publication.payment import PublicationPaymentStatus
from coda.domain.publication.publication import PublicationState


class FundingRequestListMapper:
    @staticmethod
    def prefetch(
        qs: QuerySet[FundingRequestModel], prefix: str = ""
    ) -> QuerySet[FundingRequestModel]:
        return qs.select_related(
            "review",
            "publication__article_journal",
            "publication__article_journal__publisher",
            "publication__monograph_publisher",
        ).prefetch_related(
            Prefetch(
                "publication__relevant_authors",
                queryset=AuthorDomainMapper.prefetch(AuthorModel.objects.all()),
            ),
            "publication__attached_contracts__contract",
            Prefetch(
                "labels",
                queryset=Label.objects.order_by("name"),
            ),
        )

    @staticmethod
    def map(
        model: FundingRequestModel,
        payment_status: PublicationPaymentStatus,
    ) -> FundingRequestListItem:
        payment_detail = PaymentDetailMapper.map(payment_status, model.request_id)
        publication_state = PublicationState.parse(
            model.publication.publication_state,
            online=model.publication.online_publication_date,
            print=model.publication.print_publication_date,
        )
        if model.publication.article_journal is not None:
            journal = model.publication.article_journal
            return FundingRequestListItem(
                type="Article",
                id=model.pk,
                url=model.get_absolute_url(),
                publication_title=model.publication.title,
                authors=[a.name for a in model.publication.relevant_authors.all()],
                publishing_entity_type="Journal",
                publishing_entity_name=journal.title,
                publishing_entity_url=journal.get_absolute_url(),
                updated_at=model.updated_at.date(),
                labels=model.labels.all(),
                status=model.review.review_result,
                payment_status=payment_detail,
                journal_publisher_name=str(journal.publisher) if journal.publisher else None,
                journal_publisher_url=(
                    journal.publisher.get_absolute_url() if journal.publisher else None
                ),
                has_invalid_contract_years=_has_invalid_contract_years(model),
                request_id=model.request_id,
                publication_state=publication_state.name(),
            )
        else:
            publisher = model.publication.monograph_publisher
            assert publisher is not None
            return FundingRequestListItem(
                type="Monograph",
                id=model.pk,
                url=model.get_absolute_url(),
                publication_title=model.publication.title,
                authors=[a.name for a in model.publication.relevant_authors.all()],
                publishing_entity_type="Publisher",
                publishing_entity_name=publisher.name,
                publishing_entity_url=publisher.get_absolute_url(),
                updated_at=model.updated_at.date(),
                labels=model.labels.all(),
                status=model.review.review_result,
                payment_status=payment_detail,
                journal_publisher_name=None,
                journal_publisher_url=None,
                has_invalid_contract_years=_has_invalid_contract_years(model),
                request_id=model.request_id,
                publication_state=publication_state.name(),
            )


def _has_invalid_contract_years(model: FundingRequestModel) -> bool:
    for attached_contract in model.publication.attached_contracts.all():
        contract = ContractDomainMapper.map(attached_contract.contract)
        if not ContractYear(attached_contract.contract_year, contract).is_in_contract_period():
            return True
    return False
