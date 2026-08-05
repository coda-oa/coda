import functools

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import include, path
from django.views import defaults as default_views
from django.views.decorators.http import require_GET

from coda.apps import home
from coda.apps.htmx_components.forms import DemoFormset
from coda.apps.login import CustomLoginView
from coda.apps.version import (
    check_update as check_version_update,
    get_branch,
    get_commit_sha,
    get_repo,
    get_version_tag,
)


@require_GET
def check_update(request: HttpRequest) -> HttpResponse:
    branch = get_branch()
    commit_sha = get_commit_sha()
    tag = get_version_tag()
    repo = get_repo()
    update_info = check_version_update(branch, commit_sha)
    if tag:
        github_url = f"https://github.com/{repo}/releases/tag/{tag}"
    else:
        github_url = f"https://github.com/{repo}/tree/{branch}"
    return render(
        request,
        "partials/update_banner.html",
        {
            "update_available": update_info.get("update_available", False),
            "branch": branch,
            "github_url": github_url,
        },
    )


urlpatterns = [
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # User management
    path("", home.view, name="home"),
    path("login/", view=CustomLoginView.as_view(), name="login"),
    path("logout/", view=LogoutView.as_view(), name="logout"),
    path("users/", include("coda.apps.users.urls", namespace="users")),
    path("contracts/", include("coda.apps.contracts.urls", namespace="contracts")),
    path("publishing/", include("coda.apps.publishing.urls", namespace="publishing")),
    path("authors/", include("coda.apps.authors.urls", namespace="authors")),
    path("institutions/", include("coda.apps.institutions.urls", namespace="institutions")),
    path(
        "fundingrequests/", include("coda.apps.fundingrequests.urls", namespace="fundingrequests")
    ),
    path("publications/", include("coda.apps.publications.urls", namespace="publications")),
    path("invoices/", include("coda.apps.invoices.urls", namespace="invoices")),
    path("preferences/", include("coda.apps.preferences.urls", namespace="preferences")),
    path("blocklist/", include("coda.apps.blocklist.urls", namespace="blocklist")),
    path("infopage/", include("coda.apps.infopage.urls", namespace="infopage")),
    path("opencost/", include("coda.apps.opencost.urls", namespace="opencost")),
    path("exports/", include("coda.apps.exports.urls", namespace="exports")),
    path("check-update/", check_update, name="check_update"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    demo_formset_view = DemoFormset.get_management_view()
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
        path(
            "demo/",
            lambda req: render(
                req,
                "demo.html",
                {"formset": DemoFormset(prefix="f1"), "formset2": DemoFormset(prefix="f2")},
            ),
        ),
        path("demo/htmx/", demo_formset_view.as_view(), name=demo_formset_view.name),
        path("silk/", include("silk.urls", namespace="silk")),
    ]
