from typing import Any, cast

from django import forms
from django.http import HttpRequest, HttpResponse
from django.template import Context, Engine, Template, engines
from django.template.response import TemplateResponse
from django.utils.datastructures import MultiValueDict
from django.views import View


def _template_string(url_name: str) -> str:
    return f"""
    <div class="htmx-formset-wrapper">
        <input type="hidden" name="total_forms" value="{{{{ total_forms }}}}">
        {{% for form in formset %}}
            {{{{ form.as_p }}}}
            <button type="button" hx-swap="outerHTML" hx-target="closest div.htmx-formset-wrapper">Remove</button>
        {{% endfor %}}
        <button type="button" hx-post="{{% url '{url_name}' %}}" hx-swap="outerHTML" hx-target="closest div.htmx-formset-wrapper">Add</button>
    </div>
    """


BACKEND = engines["django"]


class ManagementView(View):
    name: str
    form_class: type[forms.Form]
    min_forms: int = 1

    def get(self, request: HttpRequest) -> HttpResponse:
        return TemplateResponse(
            request, self.get_template(), self.get_context(request, self.min_forms)
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        return TemplateResponse(
            request, self.get_template(), self.get_context(request, self.total_forms + 1)
        )

    def delete(self, request: HttpRequest) -> HttpResponse:
        return TemplateResponse(
            request, self.get_template(), self.get_context(request, self.total_forms - 1)
        )

    @property
    def total_forms(self) -> int:
        return int(self.request.POST.get("total_forms", self.min_forms))

    def get_context(self, request: HttpRequest, total_forms: int) -> dict[str, Any]:
        formset = [self.form_class(request.POST) for _ in range(int(total_forms))]
        return {"total_forms": total_forms, "formset": formset}

    def get_template(self) -> Template:
        # TODO: This cast is incorrect as BACKEND.from_string returns a _EngineTemplate, not a regular Template
        return cast(Template, BACKEND.from_string(_template_string(self.name)))


class HtmxDynamicFormset:
    name: str
    form_class: type[forms.Form]

    def __init__(
        self,
        data: MultiValueDict[str, str] | None = None,
        form_class: type[forms.Form] | None = None,
    ) -> None:
        self.data = data
        self.form_class = form_class or self.form_class
        if not issubclass(self.form_class, forms.Form):
            raise TypeError("form_class must be a subclass of django.forms.Form")

    @classmethod
    def get_management_view(cls) -> type[ManagementView]:
        class _ManagementView(ManagementView):
            name = cls.name
            form_class = cls.form_class

        return _ManagementView

    def __str__(self) -> str:
        return (
            Engine.get_default()
            .from_string(_template_string(self.name))
            .render(Context({"formset": [self.form_class()]}))
        )


class DemoForm(forms.Form):
    name = forms.CharField()


class DemoFormset(HtmxDynamicFormset):
    form_class = DemoForm
    name = "demo_htmx"
