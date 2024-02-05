from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.generic import DetailView, TemplateView

from coda.apps.authors.forms import PersonForm
from coda.apps.authors.models import Author, Person


class AuthorDetailView(DetailView[Author]):
    model = Author
    template_name = "authors/author_detail.html"
    context_object_name = "author"


class AuthorCreateView(TemplateView):
    template_name = "authors/author_create.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx.update({"person_form": PersonForm()})
        return ctx

    def post(self, request: HttpRequest) -> HttpResponse:
        person_form = PersonForm(request.POST)
        if person_form.is_valid():
            author = self.save_author(person_form)
            return redirect("authors:detail", pk=author.pk)
        else:
            self.add_error_messages(request, person_form)
            return redirect("authors:create")

    def save_author(self, person_form: PersonForm) -> Author:
        person: Person = person_form.save(commit=False)
        person.full_clean()
        person.save()

        author, _ = Author.objects.get_or_create(details=person, affiliation=None)
        author.full_clean()
        author.save()
        return author

    def add_error_messages(self, request: HttpRequest, person_form: PersonForm) -> None:
        for field, errors in person_form.errors.items():
            field_hint = f"{field}:" if field != "__all__" else ""
            for error in errors:
                msg = f"{field_hint} {error}"
                messages.error(request, msg)
