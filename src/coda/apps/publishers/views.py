from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView, ListView

from coda.apps.publishers.models import Publisher


class PublisherDetailView(LoginRequiredMixin, DetailView[Publisher]):
    model = Publisher
    slug_field = "publisher__slug"
    slug_url_kwarg = "slug"


publisher_detail_view = PublisherDetailView.as_view()


class PublisherListView(LoginRequiredMixin, ListView[Publisher]):
    model = Publisher


publisher_list_view = PublisherListView.as_view()
