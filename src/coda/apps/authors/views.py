from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.generic import DetailView, TemplateView

from coda.apps.authors.forms import AuthorForm
from coda.apps.authors.models import Author
from coda.apps.authors.services import author_create


class AuthorDetailView(DetailView[Author]):
    model = Author
    template_name = "authors/author_detail.html"
    context_object_name = "author"


class AuthorCreateView(TemplateView):
    template_name = "authors/author_create.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["author_form"] = AuthorForm()
        return ctx

    def post(self, request: HttpRequest) -> HttpResponse:
        person_form = AuthorForm(request.POST)
        if person_form.is_valid():
            author_id = author_create(person_form.to_author())
            return redirect("authors:detail", pk=author_id)
        else:
            self.add_error_messages(request, person_form)
            return redirect("authors:create")

    def add_error_messages(self, request: HttpRequest, person_form: AuthorForm) -> None:
        for field, errors in person_form.errors.items():
            field_hint = f"{field}:" if field != "__all__" else ""
            for error in errors:
                msg = f"{field_hint} {error}"
                messages.error(request, msg)
