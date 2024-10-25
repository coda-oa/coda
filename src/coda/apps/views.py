from typing import Any, Generic, TypeVar

from django.core.paginator import Paginator
from django.http import HttpRequest
from django.views.generic import TemplateView

EntityType = TypeVar("EntityType")


class EntityListView(Generic[EntityType], TemplateView):
    template_name = "entity_list_page.html"
    paginate_by = 10
    entity_name: str
    entity_create_url: str
    entity_list_item_template: str
    entity_list_layout_classes: str = ""
    entity_filter_template: str = ""

    def get_entities(self, request: HttpRequest) -> list[EntityType]:
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
            "entities": page.object_list,
            "page_obj": page,
        }
