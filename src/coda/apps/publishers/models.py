from django.db import models
from django.urls import reverse
from django.utils.http import urlencode


class Publisher(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_absolute_url(self) -> str:
        """Publishers currently have no detail view. Therefore, the list view is returned."""
        listview_url = reverse("publishing:publishers:list")
        encoded_query_string = urlencode({"query": self.name})
        return f"{listview_url}?{encoded_query_string}"

    def __str__(self) -> str:
        return self.name
