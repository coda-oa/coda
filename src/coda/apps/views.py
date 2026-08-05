from collections.abc import Sequence
from typing import Any, Generic, TypeVar, cast

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from coda.apps.version import (
    check_update as check_version_update,
    get_branch,
    get_commit_sha,
    get_repo,
    get_version_tag,
)

from coda.apps.version import (
    check_update as check_version_update,
    get_branch,
    get_commit_sha,
    get_repo,
    get_version_tag,
)

from django.db.models import Model 

from coda.apps.domainqueryset import DomainQuerySet
from coda.apps.search import words_icontains

EntityType = TypeVar("EntityType")


@require_GET
def check_update(request: HttpRequest) -> HttpResponse:
    branch = get_branch()
    commit_sha = get_commit_sha()
    tag = get_version_tag()
    repo = get_repo()
    update_info = check_version_update(branch, commit_sha)
    if tag:
        github_url = f"https://github.com/{repo}/releases/tag/{tag}"
    else:
        github_url = f"https://github.com/{repo}/tree/{branch}"
    return render(
        request,
        "partials/update_banner.html",
        {
            "update_available": update_info.get("update_available", False),
            "branch": branch,
            "github_url": github_url,
        },
    )


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
    ordering: list[str] | None = None

    def get_entities(self, request: HttpRequest) -> Sequence[ModelType]:
        search_term = request.GET.get("query", "").strip()
        queryset = self.model.objects.all()  # type: ignore[attr-defined]

        if search_term:
            queryset = queryset.filter(words_icontains(search_term, *self.search_fields))

        order = self.ordering or self.search_fields
        return DomainQuerySet(queryset.order_by(*order), lambda x: cast(ModelType, x))
