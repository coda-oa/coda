from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest
from django.urls import reverse
from django.utils.functional import cached_property

from coda.apps.breadcrumbs.decorators import breadcrumb
from coda.apps.contracts.models import Contract
from coda.apps.domainqueryset import LazyBulkQuerySet
from coda.apps.fundingrequests import fundingrequest_query as fq
from coda.apps.fundingrequests.forms import FundingRequestListFilterForm
from coda.apps.fundingrequests.models import Label
from coda.apps.fundingrequests.queries import list as list_query
from coda.apps.fundingrequests.queries.models import FundingRequestListItem
from coda.apps.listfilters import ListRegionMixin, build_filter_summary, params_without
from coda.apps.views import EntityListView


@breadcrumb("Funding Requests", parent_url_name="fundingrequests:home")
class FundingRequestListView(LoginRequiredMixin, EntityListView[FundingRequestListItem]):
    template_name = "fundingrequests/fundingrequest_list.html"
    entity_name = "Funding Requests"
    entity_create_url = "fundingrequests:create_wizard"
    entity_list_item_template = "fundingrequests/fundingrequest_list_item.html"

    @cached_property
    def _used_labels(self) -> list[Label]:
        """Labels attached to at least one request — the only filterable set."""
        return list(Label.objects.filter(requests__isnull=False).distinct().order_by("name"))

    def get_entities(self, request: HttpRequest) -> Sequence[FundingRequestListItem]:
        filter_form = FundingRequestListFilterForm(request.GET, labels=self._used_labels)
        criteria, sort_order = filter_form.search_criteria()
        django_queryset = fq.search(*criteria, sort_order=fq.SortOrder[sort_order.name])
        return LazyBulkQuerySet(
            queryset=django_queryset,
            bulk_converter=list_query.get_list_items,
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_contract_list_context())
        ctx["query"] = self.request.GET.get("search_term", "")
        if self.request.GET:
            ctx["no_results_message"] = "No funding requests match the selected filters."
            ctx["no_results_clear_url"] = reverse("fundingrequests:list")

        labels = self._used_labels
        filter_form = FundingRequestListFilterForm(
            self.request.GET,
            contracts=ctx["contract_list"],
            labels=labels,
        )
        filter_form.is_valid()
        date_errors = filter_form.errors.get("date_range")
        date_range_error = str(date_errors[0]) if date_errors else None
        summary = build_filter_summary(
            self.request,
            labels,
            ctx["contract_list"],
            included=filter_form.selected_label_ids,
            excluded=filter_form.excluded_label_ids,
            list_url_name=_LISTVIEW_URL,
            region_url_name=_LIST_REGION_URL,
            date_range=filter_form.cleaned_data.get("date_range"),
            date_range_error=date_range_error,
        )

        return ctx | {
            "labels": labels,
            "label_pills": build_label_pills(
                self.request, labels, included=filter_form.selected_label_ids
            ),
            "filter_count": summary.count,
            "filter_errors": summary.errors,
            "label_state": sorted(filter_form.selected_label_ids),
            "active_filters": summary.chips,
            "filter_form": filter_form,
        }


_LISTVIEW_URL = "fundingrequests:list"
_LIST_REGION_URL = "fundingrequests:list_region"


class FundingRequestListRegionView(ListRegionMixin, FundingRequestListView):
    template_name = "fundingrequests/fundingrequest_filtered_list.html"
    list_url_name = _LISTVIEW_URL


fundingrequest_list = FundingRequestListView.as_view()
fundingrequest_list_region = FundingRequestListRegionView.as_view()


def get_contract_list_context() -> dict[str, Any]:
    return {"contract_list": Contract.objects.all()}


@dataclass(frozen=True)
class LabelPill:
    name: str
    color: str
    state: Literal["default", "included"]
    toggle_url: str
    toggle_fragment_url: str


def _pill_url(request: HttpRequest, url_name: str, *, labels: set[int]) -> str:
    params = params_without(request.GET, "labels", "page")
    if labels:
        params.setlist("labels", [str(x) for x in sorted(labels)])
    return reverse(url_name, query=params or None)


def label_pill_url(request: HttpRequest, *, labels: set[int]) -> str:
    """Build the list URL for a given label filter state.

    Preserves all current GET params except ``labels`` and ``page``, then sets
    the new label list. An empty list is omitted. ``exclude_labels`` is
    managed by the advanced-search.
    """
    return _pill_url(request, _LISTVIEW_URL, labels=labels)


def label_pill_fragment_url(request: HttpRequest, *, labels: set[int]) -> str:
    """List-region variant of `label_pill_url` for in-place list updates."""
    return _pill_url(request, _LIST_REGION_URL, labels=labels)


def build_label_pills(
    request: HttpRequest, labels: Sequence[Label], *, included: set[int]
) -> list[LabelPill]:
    """One pill per label.

    Labels in ``included`` render selected and their toggle removes them from
    the label filter; every other label renders plain and its toggle adds it.
    """
    return [
        LabelPill(
            name=label.name,
            color=label.hexcolor,
            state="included" if label.pk in included else "default",
            toggle_url=label_pill_url(request, labels=included ^ {label.pk}),
            toggle_fragment_url=label_pill_fragment_url(request, labels=included ^ {label.pk}),
        )
        for label in labels
    ]
