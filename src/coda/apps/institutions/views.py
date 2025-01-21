from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse

from coda.apps.institutions.models import Institution
from coda.apps.institutions import repository
from coda.apps.views import EntityListView


class InstitutionListView(LoginRequiredMixin, EntityListView[Institution]):
    entity_name = "Institution"
    entity_filter_template = "institutions/institution_filter.html"
    entity_list_item_template = "institutions/institution_list_item.html"

    def get_entities(self, request: HttpRequest) -> list[Institution]:
        return list(repository.search(name=request.GET.get("query")))


institution_list_view = InstitutionListView.as_view()


@login_required
def toggle_selectable(request: HttpRequest, pk: int) -> HttpResponse:
    institution = Institution.objects.get(pk=pk)
    institution.virtual = not institution.virtual
    institution.save()
    return HttpResponse()
