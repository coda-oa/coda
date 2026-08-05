from collections.abc import Sequence
from typing import Any, Generic, TypeVar, cast

from django.core.paginator import Paginator
from django.http import HttpRequest
from django.views.generic import TemplateView

from django.db.models import Model

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.search import words_icontains

EntityType = TypeVar("EntityType")


class EntityListView(Generic[EntityType], TemplateView):
    template_name = "entity_list_page.html"
    paginate_by = 10
    entity_name: str
    entity_create_url: str = ""
    entity_list_item_template: str
    entity_list_layout_classes: str = ""
    entity_filter_template: str = ""
    use_generic_entity_filter: bool = False
    supports_archiving: bool = False

    def get_entities(self, request: HttpRequest) -> Sequence[EntityType]:
        raise NotImplementedError

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        paginator = Paginator(self.get_entities(self.request), per_page=self.paginate_by)
        page = paginator.get_page(self.request.GET.get("page"))

        return {
            "entity_name": self.entity_name,
            "entity_create_url": self.entity_create_url,
            "entity_list_item_template": self.entity_list_item_template,
            "entity_filter_template": self.entity_filter_template,
            "entity_list_layout_classes": self.entity_list_layout_classes,
            "use_generic_entity_filter": self.use_generic_entity_filter,
            "supports_archiving": self.supports_archiving,
            "entities": page.object_list,
            "page_obj": page,
            "search_placeholder": self.search_placeholder,
        }

    @property
    def search_placeholder(self) -> str:
        return f"Search {self.entity_name.lower()}..."


ModelType = TypeVar("ModelType", bound=Model)


class SimpleSearchEntityListView(EntityListView[ModelType], Generic[ModelType]):
    model: type[ModelType]
    search_fields: list[str] = ["name"]

    def get_entities(self, request: HttpRequest) -> Sequence[ModelType]:
        search_term = request.GET.get("query", "").strip()
        queryset = self.model.objects.all()  # type: ignore[attr-defined]

        if search_term:
            queryset = queryset.filter(words_icontains(search_term, *self.search_fields))

        return DomainQuerySet(queryset.order_by(*self.search_fields), lambda x: cast(ModelType, x))
