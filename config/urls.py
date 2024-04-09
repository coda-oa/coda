from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView
from django.urls import include, path
from django.views import defaults as default_views

from coda.apps import home

urlpatterns = [
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # User management
    path("", home.view, name="home"),
    path("login/", view=LoginView.as_view(template_name="pages/login.html"), name="login"),
    path("users/", include("coda.apps.users.urls", namespace="users")),
    path("contracts/", include("coda.apps.contracts.urls", namespace="contracts")),
    path("journals/", include("coda.apps.journals.urls", namespace="journals")),
    path("publishers/", include("coda.apps.publishers.urls", namespace="publishers")),
    path("authors/", include("coda.apps.authors.urls", namespace="authors")),
    path(
        "fundingrequests/", include("coda.apps.fundingrequests.urls", namespace="fundingrequests")
    ),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
