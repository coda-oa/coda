from collections.abc import Sequence

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest
from django.views.generic import CreateView, DetailView

from coda.apps.journals import services
from coda.apps.journals.forms import JournalForm
from coda.apps.journals.models import Journal
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

    def get_entities(self, request: HttpRequest) -> Sequence[Journal]:
        search_term = self.request.GET.get("search_term", "")
        if search_term:
            return services.find_by_title(search_term)

        return services.all()


journal_list_view = JournalListView.as_view()


class JournalCreateView(LoginRequiredMixin, CreateView[Journal, JournalForm]):
    form_class = JournalForm
    template_name = "generic_form_view.html"


journal_create_view = JournalCreateView.as_view()
