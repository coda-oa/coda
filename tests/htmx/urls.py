from django.urls import path

from tests.htmx.views import _TestFormset, formset_view

management_view = _TestFormset.get_management_view()
urlpatterns = [
    path("", formset_view, name="formset_view"),
    path("multi/", formset_view, name="multi_formset_view"),
    path("htmx/", management_view.as_view(), name=management_view.name),
]
