from typing import cast

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.generic import DetailView, TemplateView

from coda import orcid
from coda.apps.authors.models import Author, Person


class AuthorDetailView(DetailView[Author]):
    model = Author
    template_name = "authors/author_detail.html"
    context_object_name = "author"


class AuthorCreateView(TemplateView):
    template_name = "authors/author_create.html"

    def validate_email(self, email: str | None) -> str:
        validate_email(email)
        return cast(str, email)

    def validate_name(self, name: str | None) -> str:
        if not name:
            raise ValidationError("Name is required")

        if len(name) > 255:
            raise ValidationError("Name is too long")

        if "\0" in name:
            raise ValidationError("Name contains illegal characters")

        return name

    def post(self, request: HttpRequest) -> HttpResponse:
        post = request.POST
        name = self.validate_name(post.get("name"))
        email = self.validate_email(post.get("email"))
        _orcid = orcid.parse(post.get("orcid"))
        details = Person.objects.create(name=name, email=email, orcid=_orcid)
        author = Author.objects.create(details=details)

        return redirect("authors:detail", pk=author.pk)
