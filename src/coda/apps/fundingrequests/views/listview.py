from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel, Label


from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.views.generic import ListView


from typing import Any, cast


class FundingRequestListView(LoginRequiredMixin, ListView[FundingRequestModel]):
    model = FundingRequestModel
    template_name = "fundingrequests/fundingrequest_list.html"
    context_object_name = "funding_requests"
    paginate_by = 10

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["labels"] = Label.objects.all()
        context["processing_states"] = FundingRequestModel.PROCESSING_CHOICES
        return context

    def get_queryset(self) -> QuerySet[FundingRequestModel]:
        search_type = self.request.GET.get("search_type")
        if search_type in ["title", "submitter"]:
            search_args = {search_type: self.request.GET.get("search_term")}
        else:
            search_args = {}

        return cast(
            QuerySet[FundingRequestModel],
            repository.search(
                **search_args,
                labels=list(map(int, self.request.GET.getlist("labels"))),
                processing_states=self.request.GET.getlist("processing_status"),
            ),
        )
