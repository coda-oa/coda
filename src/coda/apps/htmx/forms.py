import logging
from typing import Any, cast

from django import forms
from django.http import HttpRequest, HttpResponse, QueryDict
from django.template import Context, Engine, Template, engines
from django.template.response import TemplateResponse
from django.utils.datastructures import MultiValueDict
from django.views import View


def _template_string(url_name: str) -> str:
    return f"""
    <div class="htmx-formset-wrapper">
        <p>{{{{ total_forms }}}} forms</p>
        <input type="hidden" name="total_forms" value="{{{{ total_forms }}}}">
        {{% for form in formset %}}
            {{{{ form.as_p }}}}
            <button type="button" name="form_action_delete" value="{{{{ forloop.counter }}}}" hx-post="{{% url '{url_name}' %}}" hx-swap="outerHTML" hx-target="closest div.htmx-formset-wrapper">Remove</button>
        {{% endfor %}}
        <button type="button" name="form_action_add" value="add_form" hx-post="{{% url '{url_name}' %}}" hx-swap="outerHTML" hx-target="closest div.htmx-formset-wrapper">Add</button>
    </div>
    """


BACKEND = engines["django"]


class ManagementView(View):
    name: str
    form_class: type[forms.Form]
    min_forms: int = 1

    def get(self, request: HttpRequest) -> HttpResponse:
        return self._get_response(request, self.min_forms)

    def post(self, request: HttpRequest) -> HttpResponse:
        if request.POST.get("form_action_add") is not None:
            return self._get_response(request, self.total_forms() + 1)
        elif (form_index := request.POST.get("form_action_delete")) is not None:
            formset = self._get_forms(request, int(form_index))
            logging.error(f"Prefixes {[f.prefix for f in formset]}")
            for i, f in enumerate(formset, start=1):
                logging.error(f"Setting prefix of form '{f.prefix}' to 'form-{i}'")
                f.prefix = f"form-{i}"
            context = {"total_forms": len(formset), "formset": formset}
            return TemplateResponse(request, self._get_template(), context)

        else:
            return self._get_response(request, self.total_forms())

    def _get_forms(self, request: HttpRequest, exclude_index: int) -> list[forms.Form]:
        return [
            self.form_class(request.POST, prefix=f"form-{form_index}")
            for form_index in range(1, self.total_forms() + 1)
            if form_index != exclude_index
        ]

    def _get_response(self, request: HttpRequest, total_forms: int) -> HttpResponse:
        return TemplateResponse(
            request, self._get_template(), self.get_context(request, total_forms)
        )

    def total_forms(self, query_dict: QueryDict | None = None) -> int:
        query_dict = query_dict or self.request.POST
        return int(query_dict.get("total_forms", self.min_forms) or self.min_forms)

    def get_context(self, request: HttpRequest, total_forms: int) -> dict[str, Any]:
        formset = [
            self.form_class(request.POST, prefix=f"form-{form_index + 1}")
            for form_index in range(total_forms)
        ]
        return {"total_forms": total_forms, "formset": formset}

    def _get_template(self) -> Template:
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
        if not self.name:
            raise ValueError("name is required")

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
            .render(Context({"formset": [self.form_class(prefix="form-1")], "total_forms": 1}))
        )


class DemoForm(forms.Form):
    name = forms.CharField()


class DemoFormset(HtmxDynamicFormset):
    form_class = DemoForm
    name = "demo_htmx"
