from django.apps import AppConfig


class ExportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "coda.apps.exports"
    verbose_name = "Exports"

    def ready(self) -> None:
        import coda.apps.exports.signals  # noqa
