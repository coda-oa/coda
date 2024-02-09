from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.generic import DetailView, TemplateView

from coda.apps.authors.forms import PersonForm
from coda.apps.authors.models import Author
from coda.apps.institutions.models import Institution


class AuthorDetailView(DetailView[Author]):
    model = Author
    template_name = "authors/author_detail.html"
    context_object_name = "author"


class AuthorCreateView(TemplateView):
    template_name = "authors/author_create.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx.update({"person_form": PersonForm(), "institution_list": Institution.objects.all()})
        return ctx

    def post(self, request: HttpRequest) -> HttpResponse:
        person_form = PersonForm(request.POST)
        if person_form.is_valid():
            affiliation_pk = request.POST.get("affiliation")
            author = self.save_author(person_form, affiliation_pk)
            return redirect("authors:detail", pk=author.pk)
        else:
            self.add_error_messages(request, person_form)
            return redirect("authors:create")

    def save_author(self, person_form: PersonForm, affiliation_pk: Any) -> Author:
        return Author.create(**person_form.cleaned_data, affiliation_pk=affiliation_pk)

    def add_error_messages(self, request: HttpRequest, person_form: PersonForm) -> None:
        for field, errors in person_form.errors.items():
            field_hint = f"{field}:" if field != "__all__" else ""
            for error in errors:
                msg = f"{field_hint} {error}"
                messages.error(request, msg)
