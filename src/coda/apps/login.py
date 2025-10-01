

from django.contrib.auth.views import LoginView as DjangoLoginView
from django.utils.decorators import method_decorator
from coda.apps.breadcrumbs.decorators import breadcrumb

@method_decorator(breadcrumb("Login"), name="dispatch")
class CustomLoginView(DjangoLoginView):
    template_name = "pages/login.html"