from django.http import HttpRequest
from django_htmx.middleware import HtmxDetails


class HtmxHttpRequest(HttpRequest):
    """HttpRequest guaranteed to carry ``htmx`` (set by HtmxMiddleware).

    Use as the request annotation in views that read ``request.htmx``,
    per the django-htmx typing pattern.
    """

    htmx: HtmxDetails
