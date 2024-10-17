from functools import cache, cached_property
from typing import Any, Generic, TypeVar

from django import forms
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils.datastructures import MultiValueDict
from django.views import View

FormType = TypeVar("FormType", bound=forms.Form)

_DEFAULT_RENDER_MODE = "paragraph"


def _total_forms(data: dict[str, Any], min_forms: int = 1) -> int:
    return int(data.get("total_forms", min_forms) or min_forms)


def _forms(
    data: dict[str, Any], num_forms: int, form_class: type[FormType], prefix: str | None = None
) -> list[FormType]:
    prefix = prefix or data.get("prefix")
    if prefix:
        prefix = f"{prefix}-"
    else:
        prefix = ""

    data.update(_initial_values(data, num_forms, prefix))

    return [
        form_class(data or None, prefix=prefix + f"form-{form_index}")
        for form_index in range(1, num_forms + 1)
    ]


def _initial_values(data: dict[str, Any], num_forms: int, prefix: str) -> dict[str, Any]:
    initial_prefix = "initial-"
    return {
        prefix + f"form-{num_forms}-{key.removeprefix(initial_prefix)}": value
        for key, value in data.items()
        if key.startswith(initial_prefix)
    }


def _context(
    forms: list[FormType], name: str, mode: str | None, prefix: str | None
) -> dict[str, Any]:
    return {
        "total_forms": len(forms),
        "formset": forms,
        "url_name": name,
        "prefix": prefix,
        "mode": mode or _DEFAULT_RENDER_MODE,
    }


class HtmxDynamicFormset(Generic[FormType]):
    name: str
    form_class: type[FormType]

    template_name = "htmx_formset.html"

    @classmethod
    def get_management_view(cls) -> type["ManagementView[FormType]"]:
        class _ManagementView(ManagementView[FormType]):
            name = cls.name
            form_class: type[FormType] = cls.form_class
            template_name = cls.template_name

        return _ManagementView

    def __init__(
        self,
        data: MultiValueDict[str, str] | None = None,
        *,
        form_class: type[FormType] | None = None,
        prefix: str | None = None,
    ) -> None:
        self._data = data or MultiValueDict()
        self.form_class = form_class or self.form_class
        self.prefix = prefix
        if not self.name:
            raise ValueError("name is required")

        if not issubclass(self.form_class, forms.Form):
            raise TypeError("form_class must be a subclass of django.forms.Form")

    @cached_property
    def forms(self) -> list[FormType]:
        total_forms = _total_forms(self._data)
        return _forms(self._data, total_forms, self.form_class, self.prefix)

    @cached_property
    def data(self) -> list[dict[str, Any]]:
        _forms = self.forms
        for form in _forms:
            form.full_clean()

        return [form.cleaned_data for form in _forms]

    @cache
    def is_valid(self) -> bool:
        return all(form.is_valid() for form in self.forms)

    def render(self, mode: str = _DEFAULT_RENDER_MODE) -> str:
        return render_to_string(
            self.template_name, _context(self.forms, self.name, mode, self.prefix)
        )

    def as_p(self) -> str:
        return self.render("paragraph")

    def as_div(self) -> str:
        return self.render("div")

    def as_inline(self) -> str:
        return self.render("inline")

    def __str__(self) -> str:
        return self.render()


class ManagementView(View, Generic[FormType]):
    name: str
    form_class: type[FormType]
    min_forms: int = 1

    template_name: str

    def post(self, request: HttpRequest) -> HttpResponse:
        if request.POST.get("form_action_add") is not None:
            forms = self._forms(request.POST.dict(), self._total_forms() + 1)
            return self._get_response(request, forms)
        elif (_form_index := request.POST.get("form_action_delete")) is not None:
            form_index = int(_form_index)
            post_data = self._data_with_form_removed(request, form_index)
            total_forms = self._total_forms(post_data)
            forms = self._forms(post_data, total_forms)
            return self._get_response(request, forms)
        else:
            forms = self._forms(request.POST, self._total_forms())
            return self._get_response(request, forms)

    def _total_forms(self, query_dict: dict[str, Any] | None = None) -> int:
        query_dict = query_dict or self.request.POST
        return _total_forms(query_dict, self.min_forms)

    def _forms(self, data: dict[str, Any], num_forms: int) -> list[FormType]:
        forms = _forms(data, num_forms, self.form_class)

        for form in forms:
            form.errors.clear()

        return forms

    def _get_response(self, request: HttpRequest, forms: list[FormType]) -> HttpResponse:
        mode = request.POST.get("mode")
        prefix = request.POST.get("prefix")
        return render(request, self.template_name, _context(forms, self.name, mode, prefix))

    def _data_with_form_removed(self, request: HttpRequest, form_index: int) -> dict[str, Any]:
        post_data = request.POST.dict()
        total_forms = self._total_forms(post_data)
        post_data = self._remove_form_data(post_data, form_index)
        post_data = self._shift_form_data(post_data, form_index)
        post_data["total_forms"] = str(total_forms - 1)
        return post_data

    def _remove_form_data(self, post_data: dict[str, Any], form_index: int) -> dict[str, Any]:
        return {
            key: value
            for key, value in post_data.items()
            if not key.startswith(f"form-{form_index}-")
        }

    def _shift_form_data(self, data: dict[str, Any], form_index: int) -> dict[str, Any]:
        def new_key(key: str, index: int) -> str:
            if index > form_index:
                return key.replace(f"form-{index}-", f"form-{index - 1}-")
            return key

        return {
            new_key(key, i): value
            for key, value in data.items()
            for i in range(1, self._total_forms(data) + 1)
        }


class DemoForm(forms.Form):
    field = forms.CharField()
    field2 = forms.CharField()


class DemoFormset(HtmxDynamicFormset[DemoForm]):
    form_class = DemoForm
    name = "demo_htmx"
