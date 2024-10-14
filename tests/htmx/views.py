from django import forms
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.htmx.forms import HtmxDynamicFormset


class _TestForm(forms.Form):
    field = forms.CharField()


class _TestFormset(HtmxDynamicFormset[_TestForm]):
    name = "test_formset"
    form_class = _TestForm


def formset_view(request: HttpRequest) -> HttpResponse:
    return render(request, "htmx_formset_template.html", {"formset": _TestFormset(request.POST)})
