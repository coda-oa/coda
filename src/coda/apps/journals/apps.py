from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class JournalsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "coda.apps.journals"
    verbose_name = _("Journals")
