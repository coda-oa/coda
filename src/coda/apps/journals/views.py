from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms.utils import ErrorList
from django.http import HttpRequest, HttpResponse
from django.views.generic import CreateView, DetailView

from coda.apps.journals.forms import JournalForm
from coda.apps.journals.models import Journal
from coda.apps.journals.services import find_by_title
from coda.apps.views import EntityListView


class JournalDetailView(LoginRequiredMixin, DetailView[Journal]):
    model = Journal
    slug_field = "eissn"
    slug_url_kwarg = "eissn"


journal_detail_view = JournalDetailView.as_view()


class JournalListView(LoginRequiredMixin, EntityListView[Journal]):
    paginate_by = 20
    entity_name = "Journals"
    entity_create_url = "journals:create"
    entity_list_item_template = "journals/journal_list_item.html"
    entity_filter_template = "journals/journal_filter.html"
    entity_list_layout_classes = "grid-container"

    def get_entities(self, request: HttpRequest) -> list[Journal]:
        search_term = self.request.GET.get("search_term", "")
        if search_term:
            return list(find_by_title(search_term))

        return list(Journal.objects.all())


journal_list_view = JournalListView.as_view()


class JournalCreateView(LoginRequiredMixin, CreateView[Journal, JournalForm]):
    form_class = JournalForm
    template_name = "generic_form_view.html"

    def form_valid(self, form: JournalForm) -> HttpResponse:
        existing = Journal.objects.filter(eissn=form.instance.eissn).first()
        form.errors["eissn"] = ErrorList(["Journal with this E-ISSN already exists."])
        if existing:
            return self.form_invalid(form)

        return super().form_valid(form)


journal_create_view = JournalCreateView.as_view()
