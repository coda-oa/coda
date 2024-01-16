from typing import TYPE_CHECKING
from django.contrib.auth import forms as admin_forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from coda.apps.users.models import User  # noqa: F401

UserModel = get_user_model()


class UserAdminChangeForm(admin_forms.UserChangeForm["User"]):
    class Meta(admin_forms.UserChangeForm.Meta):
        model = UserModel


class UserAdminCreationForm(admin_forms.UserCreationForm["User"]):
    """
    Form for User Creation in the Admin Area.
    To change user signup, see UserSignupForm and UserSocialSignupForm.
    """

    class Meta(admin_forms.UserCreationForm.Meta):
        model = UserModel
        error_messages = {
            "username": {"unique": _("This username has already been taken.")},
        }
