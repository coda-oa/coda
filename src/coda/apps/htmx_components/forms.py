import json
import logging
from collections.abc import Callable, Mapping
from functools import cache, cached_property
from typing import Any, Generic, Self, TypeVar

import pydantic
from django import forms
from django.http import HttpRequest, HttpResponse
from django.template.loader import render_to_string
from django.utils.datastructures import MultiValueDict
from django.utils.safestring import mark_safe
from django.views import View

from coda.apps.htmx_components.converters import to_htmx_formset_data

FormType = TypeVar("FormType", bound=forms.Form)

_DEFAULT_RENDER_MODE = "paragraph"


def _total_forms(data: dict[str, Any], prefix: str | None, min_forms: int = 1) -> int:
    from coda.security.integration import SecureFormIntegration

    prefix = _prefix(data, prefix)
    # Extract the raw value and use our secure parsing
    try:
        raw_value = data.get(prefix + "total_forms", min_forms) or min_forms
        return SecureFormIntegration.secure_total_forms(
            {prefix + "total_forms": raw_value}, prefix, min_forms, max_forms=50
        )
    except Exception:
        return min_forms


def _forms(
    data: dict[str, Any], num_forms: int, form_class: type[FormType], prefix: str | None = None
) -> list[FormType]:
    prefix = _prefix(data, prefix)

    data.update(_initial_values(data, num_forms, prefix))

    return [
        form_class(data or None, prefix=prefix + f"form-{form_index}")
        for form_index in range(1, num_forms + 1)
    ]


def _form_id(data: dict[str, Any], prefix: str | None = None) -> str:
    return str(data.get(_prefix(data, prefix) + "form_id", ""))


def _prefix(data: dict[str, Any], prefix: str | None = None) -> str:
    prefix = prefix or data.get("prefix")
    if prefix:
        prefix = f"{prefix}-"
    else:
        prefix = ""
    return prefix


def _initial_values(data: dict[str, Any], num_forms: int, prefix: str) -> dict[str, Any]:
    initial_prefix = "initial-"
    return {
        prefix + f"form-{num_forms}-{key.removeprefix(initial_prefix)}": value
        for key, value in data.items()
        if key.startswith(initial_prefix)
    }


def _context(
    forms: list[FormType],
    *,
    name: str,
    mode: str | None,
    form_id: str | None,
    prefix: str | None,
    add_button: bool = True,
    table_classes: str = "",
) -> dict[str, Any]:
    return {
        "total_forms": len(forms),
        "formset": forms,
        "url_name": name,
        "prefix": prefix,
        "mode": mode or _DEFAULT_RENDER_MODE,
        "table_classes": table_classes,
        "add_button": add_button,
        "form_id": form_id,
    }


class HxVals(pydantic.BaseModel):
    prefix: str
    mode: str = _DEFAULT_RENDER_MODE
    hx_include: str = ""
    extras: dict[str, Any] = pydantic.Field(default_factory=dict)

    @staticmethod
    def from_mapping(mapping: Mapping[str, Any]) -> "HxVals":
        logging.info(f"Creating HxVals from mapping: {mapping}")
        mode = mapping.get("mode", _DEFAULT_RENDER_MODE)
        prefix = mapping.get("prefix", "")

        extras = {}
        if extras_json := mapping.get("extras", ""):
            try:
                extras = json.loads(extras_json)
            except (json.JSONDecodeError, TypeError):
                extras = {}

        return HxVals(
            prefix=prefix,
            mode=mode,
            hx_include=mapping.get("hx_include", ""),
            extras=extras,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "prefix": self.prefix,
            "mode": self.mode,
            "hx_include": self.hx_include,
            "extras": self.extras,
        }


def render_formset_to_string(
    template_name: str,
    forms: list[FormType],
    name: str,
    form_id: str,
    add_button: bool,
    table_classes: str,
    hxvals: HxVals,
    request: HttpRequest | None = None,
) -> str:
    return mark_safe(
        render_to_string(
            template_name,
            _context(
                forms,
                name=name,
                form_id=form_id,
                mode=hxvals.mode,
                prefix=hxvals.prefix,
                add_button=add_button,
                table_classes=table_classes,
            )
            | {"hx_include": hxvals.hx_include, "hx_vals": json.dumps(hxvals.to_dict())}
            | hxvals.extras,
            request=request,
        )
    )


class HtmxDynamicFormset(Generic[FormType]):
    name: str
    form_class: type[FormType]
    min_forms: int = 1
    add_button = True

    table_classes: str = ""
    template_name = "htmx_formset.html"

    @classmethod
    def get_management_view(cls) -> type["ManagementView[FormType]"]:
        class _ManagementView(ManagementView[FormType]):
            name = cls.name
            form_class: type[FormType] = cls.form_class
            min_forms = cls.min_forms
            add_button = cls.add_button
            template_name = cls.template_name
            table_classes = cls.table_classes
            prerender_forms = cls.prerender_forms

        return _ManagementView

    @classmethod
    def from_data(cls, data: list[dict[str, Any]], *, form_id: str = "", prefix: str = "") -> Self:
        form_data = to_htmx_formset_data(data, prefix=prefix)
        return cls(MultiValueDict(form_data), form_id=form_id, prefix=prefix)

    def __init__(
        self,
        data: MultiValueDict[str, str] | None = None,
        *,
        form_class: type[FormType] | None = None,
        form_id: str = "",
        prefix: str = "",
    ) -> None:
        self._data = data or MultiValueDict()
        self.form_class = form_class or self.form_class
        self.form_id = form_id
        self.prefix = prefix

        if not self.name:
            raise ValueError("name is required")

        if not issubclass(self.form_class, forms.Form):
            raise TypeError("form_class must be a subclass of django.forms.Form")

        if data is not None:
            _ = self.is_valid()

    @cached_property
    def forms(self) -> list[FormType]:
        prerender_hook = self.__class__.prerender_forms
        total_forms = _total_forms(self._data, self.prefix, self.min_forms)
        forms = prerender_hook(
            _forms(self._data, total_forms, self.form_class, self.prefix),
            self._data,
        )
        self._full_clean(forms)

        return forms

    def _full_clean(self, forms: list[FormType]) -> None:
        for form in forms:
            form.full_clean()

    def full_clean(self) -> None:
        self._full_clean(self.forms)

    @cached_property
    def data(self) -> list[dict[str, Any]]:
        return [form.cleaned_data for form in self.forms]

    @cache
    def is_valid(self) -> bool:
        # NOTE: we have to run a full for loop here instead of using something like all()
        # because we need to run is_valid() on all forms to ensure that all error lists are populated
        valid = True
        for form in self.forms:
            if not form.is_valid():
                valid = False

        return valid

    def render(self, mode: str = _DEFAULT_RENDER_MODE, hx_include: str = "", **kwargs: Any) -> str:
        return render_formset_to_string(
            self.template_name,
            self.forms,
            self.name,
            self.form_id,
            self.add_button,
            self.table_classes,
            HxVals(
                prefix=self.prefix,
                mode=mode,
                hx_include=hx_include,
                extras=kwargs,
            ),
        )

    @staticmethod
    def prerender_forms(
        forms: list[FormType], data: Mapping[str, Any] | None = None
    ) -> list[FormType]:
        """Hook for subclasses to perform any pre-rendering logic on the forms."""
        return forms

    def as_p(self, **kwargs: Any) -> str:
        return self.render("paragraph", **kwargs)

    def as_div(self, **kwargs: Any) -> str:
        return self.render("div", **kwargs)

    def as_inline(self, **kwargs: Any) -> str:
        return self.render("inline", **kwargs)

    def __str__(self) -> str:
        return self.render()


class ManagementView(View, Generic[FormType]):
    name: str
    form_class: type[FormType]
    add_button: bool = True
    min_forms: int = 1

    table_classes: str
    template_name: str
    prerender_forms: Callable[[list[FormType], Mapping[str, Any] | None], list[FormType]]

    def post(self, request: HttpRequest) -> HttpResponse:
        if request.POST.get("form_action_add") is not None:
            forms = self._forms(request.POST.dict(), self._total_forms() + 1)
            forms[-1].errors.clear()
            return self._get_response(request, forms)
        elif (_form_index := request.POST.get("form_action_delete")) is not None:
            from coda.security.integration import SecureFormIntegration

            form_index = SecureFormIntegration.secure_form_index(_form_index, max_index=50)
            post_data = self._data_with_form_removed(request, form_index)
            total_forms = self._total_forms(post_data)
            forms = self._forms(post_data, total_forms)
            return self._get_response(request, forms)
        else:
            forms = self._forms(request.POST, self._total_forms())
            return self._get_response(request, forms)

    def _total_forms(self, query_dict: dict[str, Any] | None = None) -> int:
        query_dict = query_dict or self.request.POST
        prefix = query_dict.get("prefix")
        return _total_forms(query_dict, prefix, self.min_forms)

    def _forms(self, data: dict[str, Any], num_forms: int) -> list[FormType]:
        forms = _forms(data, num_forms, self.form_class)
        return forms

    def _get_response(self, request: HttpRequest, forms: list[FormType]) -> HttpResponse:
        hx_vals = HxVals.from_mapping(request.POST)
        logging.info(f"ManagementView: {self.name}, hx_vals: {hx_vals}")
        form_id = _form_id(request.POST, hx_vals.prefix)

        content = render_formset_to_string(
            self.template_name,
            self.__class__.prerender_forms(forms, request.POST),
            self.name,
            form_id,
            self.add_button,
            self.table_classes,
            hx_vals,
            request=request,
        )

        return HttpResponse(content=content)

    def _data_with_form_removed(self, request: HttpRequest, form_index: int) -> dict[str, Any]:
        post_data = request.POST.dict()
        total_forms = self._total_forms(post_data)
        post_data = self._remove_form_data(post_data, form_index)
        post_data = self._shift_form_data(post_data, form_index)
        post_data[_prefix(post_data) + "total_forms"] = str(total_forms - 1)
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
