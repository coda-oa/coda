import functools

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render
from django.urls import include, path
from django.views import defaults as default_views

from coda.apps import home

urlpatterns = [
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # User management
    path("", home.view, name="home"),
    path("login/", view=LoginView.as_view(template_name="pages/login.html"), name="login"),
    path("logout/", view=LogoutView.as_view(), name="logout"),
    path("users/", include("coda.apps.users.urls", namespace="users")),
    path("contracts/", include("coda.apps.contracts.urls", namespace="contracts")),
    path("journals/", include("coda.apps.journals.urls", namespace="journals")),
    path("publishers/", include("coda.apps.publishers.urls", namespace="publishers")),
    path("authors/", include("coda.apps.authors.urls", namespace="authors")),
    path(
        "fundingrequests/", include("coda.apps.fundingrequests.urls", namespace="fundingrequests")
    ),
    path("invoices/", include("coda.apps.invoices.urls", namespace="invoices")),
    path("preferences/", include("coda.apps.preferences.urls", namespace="preferences")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            functools.partial(default_views.bad_request, template_name="pages/error_page.html"),
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            functools.partial(
                default_views.permission_denied, template_name="pages/error_page.html"
            ),
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            functools.partial(default_views.page_not_found, template_name="pages/error_page.html"),
            kwargs={"exception": Exception("Page not Found")},
        ),
        path(
            "500/",
            functools.partial(default_views.server_error, template_name="pages/error_page.html"),
        ),
        path("demo/", lambda req: render(req, "demo.html")),
    ]
