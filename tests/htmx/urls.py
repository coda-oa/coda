from django.urls import path

from tests.htmx.views import (
    _TestFormset,
    _TestFormsetWithHook,
    _ZeroFormsFormset,
    formset_view,
    modify_form_hook_view,
    zero_formset_view,
)

management_view = _TestFormset.get_management_view()
zero_management_view = _ZeroFormsFormset.get_management_view()
hook_view = _TestFormsetWithHook.get_management_view()
urlpatterns = [
    path("", formset_view, name="formset_view"),
    path("multi/", formset_view, name="multi_formset_view"),
    path("zero/", zero_formset_view, name="zero_formset_view"),
    path("htmx/", management_view.as_view(), name=management_view.name),
    path("zero-formset/", zero_management_view.as_view(), name=zero_management_view.name),
    path("modify-hook-initial/", modify_form_hook_view, name="modify_form_hook_view"),
    path("modify-hook/", hook_view.as_view(), name=hook_view.name),
]
