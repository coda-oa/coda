from typing import TYPE_CHECKING, Any, cast
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, RedirectView, UpdateView

if TYPE_CHECKING:
    from coda.django_apps.users.models import User

UserModel = get_user_model()


class UserDetailView(LoginRequiredMixin, DetailView):
    model = UserModel
    slug_field = "username"
    slug_url_kwarg = "username"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = UserModel
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self) -> str:
        assert self.request.user.is_authenticated  # for mypy to know that the user is authenticated
        user = cast("User", self.request.user)
        return user.get_absolute_url()

    def get_object(self, queryset: QuerySet[Any] | None = None) -> "User":
        user = cast("User", self.request.user)
        return user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self, *args: Any, **kwargs: Any) -> str:
        user = cast("User", self.request.user)
        return reverse("users:detail", kwargs={"username": user.username})


user_redirect_view = UserRedirectView.as_view()
