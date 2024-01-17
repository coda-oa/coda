from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView

from coda.apps.journals.models import Journal


class JournalDetailView(LoginRequiredMixin, DetailView[Journal]):
    model = Journal


journal_detail_view = JournalDetailView.as_view()
