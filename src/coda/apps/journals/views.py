from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView

from coda.apps.journals.models import Journal


class JournalDetailView(LoginRequiredMixin, DetailView[Journal]):
    model = Journal
    slug_field = "eissn"
    slug_url_kwarg = "eissn"


journal_detail_view = JournalDetailView.as_view()


class JournalListView(LoginRequiredMixin, ListView[Journal]):
    model = Journal
    paginate_by = 20


journal_list_view = JournalListView.as_view()
