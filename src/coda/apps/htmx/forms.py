from collections.abc import Mapping
from functools import cache, cached_property
from typing import Any, Generic, TypeVar, cast

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
            <button type="button" name="form_action_delete" value="{{{{ forloop.counter }}}}" hx-post="{{% url '{url_name}' %}}" hx-swap="outerHTML" hx-target="closest div.htmx-formset-wrapper">Remove</button>
        {{% endfor %}}
        <button type="button" name="form_action_add" value="add_form" hx-post="{{% url '{url_name}' %}}" hx-swap="outerHTML" hx-target="closest div.htmx-formset-wrapper">Add</button>
    </div>
    """


BACKEND = engines["django"]

FormType = TypeVar("FormType", bound=forms.Form)


class ManagementView(View, Generic[FormType]):
    name: str
    form_class: type[FormType]
    min_forms: int = 1

    def get(self, request: HttpRequest) -> HttpResponse:
        return self._get_response(request, self.min_forms)

    def post(self, request: HttpRequest) -> HttpResponse:
        if request.POST.get("form_action_add") is not None:
            return self._get_response(request, self.total_forms() + 1)
        elif (_form_index := request.POST.get("form_action_delete")) is not None:
            form_index = int(_form_index)
            formset = self._get_reduced_formset(request, form_index)
            context = {"total_forms": len(formset), "formset": formset}
            return TemplateResponse(request, self._get_template(), context)
        else:
            return self._get_response(request, self.total_forms())

    def _get_reduced_formset(self, request: HttpRequest, form_index: int) -> list[FormType]:
        post_data = request.POST.dict()
        total_forms = self.total_forms(post_data)
        post_data = self._remove_form_data(post_data, form_index)
        post_data = self._shift_form_data(post_data, form_index)
        post_data["total_forms"] = str(total_forms - 1)
        return self._get_forms(post_data, total_forms - 1)

    def _remove_form_data(self, post_data: dict[str, Any], form_index: int) -> dict[str, Any]:
        return {
            key: value
            for key, value in post_data.items()
            if not key.startswith(f"form-{form_index}-")
        }

    def _shift_form_data(self, post_data: dict[str, Any], form_index: int) -> dict[str, Any]:
        def new_key(key: str, index: int) -> str:
            if index > form_index:
                return key.replace(f"form-{index}-", f"form-{index - 1}-")
            return key

        return {
            new_key(key, i): value
            for key, value in post_data.items()
            for i in range(1, self.total_forms(post_data) + 1)
        }

    def _get_forms(self, data: Mapping[str, Any], num_forms: int) -> list[FormType]:
        return [
            self.form_class(data, prefix=f"form-{form_index}")
            for form_index in range(1, num_forms + 1)
        ]

    def _get_response(self, request: HttpRequest, total_forms: int) -> HttpResponse:
        return TemplateResponse(
            request, self._get_template(), self.get_context(request, total_forms)
        )

    def total_forms(self, query_dict: Mapping[str, Any] | None = None) -> int:
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


class HtmxDynamicFormset(Generic[FormType]):
    name: str
    form_class: type[FormType]

    def __init__(
        self,
        data: MultiValueDict[str, str] | None = None,
        form_class: type[FormType] | None = None,
    ) -> None:
        self._data = data or MultiValueDict()
        self.form_class = form_class or self.form_class
        if not self.name:
            raise ValueError("name is required")

        if not issubclass(self.form_class, forms.Form):
            raise TypeError("form_class must be a subclass of django.forms.Form")

    @cached_property
    def forms(self) -> list[FormType]:
        total_forms = int(self._data.get("total_forms", 1))
        return [
            self.form_class(self._data, prefix=f"form-{form_index}")
            for form_index in range(1, total_forms + 1)
        ]

    @cached_property
    def data(self) -> list[dict[str, Any]]:
        _forms = self.forms
        for form in _forms:
            form.full_clean()

        return [form.cleaned_data for form in _forms]

    @cache
    def is_valid(self) -> bool:
        return all(form.is_valid() for form in self.forms)

    @classmethod
    def get_management_view(cls) -> type[ManagementView[FormType]]:
        class _ManagementView(ManagementView[FormType]):
            name = cls.name
            form_class: type[FormType] = cls.form_class

        return _ManagementView

    def __str__(self) -> str:
        return (
            Engine.get_default()
            .from_string(_template_string(self.name))
            .render(Context({"formset": [self.form_class(prefix="form-1")], "total_forms": 1}))
        )


class DemoForm(forms.Form):
    name = forms.CharField()


class DemoFormset(HtmxDynamicFormset[DemoForm]):
    form_class = DemoForm
    name = "demo_htmx"
