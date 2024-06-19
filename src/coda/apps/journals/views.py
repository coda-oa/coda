from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms.utils import ErrorList
from django.http import HttpResponse
from django.views.generic import CreateView, DetailView, ListView

from coda.apps.journals.forms import JournalForm
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
