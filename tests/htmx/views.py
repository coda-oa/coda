from django import forms
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.htmx_components.forms import HtmxDynamicFormset


class _TestForm(forms.Form):
    field = forms.CharField()


class _TestFormset(HtmxDynamicFormset[_TestForm]):
    name = "test_formset"
    form_class = _TestForm


class _ZeroFormsFormset(HtmxDynamicFormset[_TestForm]):
    name = "zero_formset"
    form_class = _TestForm
    min_forms = 0


def formset_view(request: HttpRequest) -> HttpResponse:
    return render(request, "htmx_formset_template.html", {"formset": _TestFormset(request.POST)})


def zero_formset_view(request: HttpRequest) -> HttpResponse:
    return render(
        request, "htmx_formset_template.html", {"formset": _ZeroFormsFormset(request.POST)}
    )


def multiple_formsets_view(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "htmx_multiple_formsets_template.html",
        {
            "formsets": [
                _TestFormset(request.POST, prefix="formset-1"),
                _TestFormset(request.POST, prefix="formset-2"),
            ],
        },
    )
