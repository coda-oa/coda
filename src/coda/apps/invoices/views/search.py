from typing import Any, ClassVar, Generic, TypeVar

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Model, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from coda.apps.contracts.models import Contract
from coda.apps.invoices.views.position_parsers import maybe_request_context
from coda.apps.publications.models import Publication
from coda.apps.search import (
    ScopedAlias,
    SearchFieldAliases,
    build_search_filter,
)

PUBLICATION_SEARCH_FIELD_ALIASES: SearchFieldAliases = {
    "title": "title",
    "doi": ScopedAlias("links__value", Q(links__type__name="DOI")),
    "request": "fundingrequest__request_id",
}

CONTRACT_SEARCH_FIELD_ALIASES: SearchFieldAliases = {
    "name": "name",
    "esac": ScopedAlias("links__value", Q(links__type__name="ESAC")),
}

_ModelT = TypeVar("_ModelT", bound=Model)


class SearchPickerView(LoginRequiredMixin, View, Generic[_ModelT]):
    """HTMX fragment view for one alias-scoped picker search box.

    POSTs the search box's value, filters the queryset through
    ``build_search_filter`` (words AND, quoted phrases, ``prefix:value`` terms)
    and re-renders the results fragment.
    """

    query_param: ClassVar[str]
    field_aliases: ClassVar[SearchFieldAliases]
    template_name: ClassVar[str]
    result_key: ClassVar[str]

    def get_queryset(self) -> QuerySet[_ModelT]:
        raise NotImplementedError

    def to_result(self, obj: _ModelT) -> dict[str, Any]:
        raise NotImplementedError

    def post(self, request: HttpRequest) -> HttpResponse:
        query = request.POST.get(self.query_param, "").strip()
        queryset = self.get_queryset().none()
        if query:
            queryset = (
                self.get_queryset()
                .filter(build_search_filter(query, field_aliases=self.field_aliases))
                .distinct()
            )

        context = {self.result_key: [self.to_result(obj) for obj in queryset]}
        return render(request, self.template_name, context)


class PublicationSearchPickerView(SearchPickerView[Publication]):
    query_param = "q"
    field_aliases = PUBLICATION_SEARCH_FIELD_ALIASES
    template_name = "invoices/search_publications.html"
    result_key = "publications"

    def get_queryset(self) -> QuerySet[Publication]:
        return Publication.objects.all()

    def to_result(self, publication: Publication) -> dict[str, Any]:
        return {
            "id": publication.id,
            "title": publication.title,
            "funding_request": maybe_request_context(publication).to_post_data(),
        }


class ContractSearchPickerView(SearchPickerView[Contract]):
    query_param = "contract_query"
    field_aliases = CONTRACT_SEARCH_FIELD_ALIASES
    template_name = "invoices/search_contracts.html"
    result_key = "contracts"

    def get_queryset(self) -> QuerySet[Contract]:
        return Contract.objects.all()

    def to_result(self, contract: Contract) -> dict[str, Any]:
        return {
            "id": contract.id,
            "name": contract.name,
            "url": reverse("contracts:detail", kwargs={"pk": contract.id}),
        }
