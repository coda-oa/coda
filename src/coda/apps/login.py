from django.contrib.auth.views import LoginView as DjangoLoginView
from coda.apps.breadcrumbs.decorators import breadcrumb


@breadcrumb("Login")
class CustomLoginView(DjangoLoginView):
    template_name = "pages/login.html"
