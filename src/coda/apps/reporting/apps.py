from django.apps import AppConfig


class StatisticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "coda.apps.reporting"
    verbose_name = "Statistics"

    def ready(self) -> None:
        # The fact cache's invalidation receivers must exist in every
        # process that serves statistics (or writes fact-relevant data).
        from coda.apps.reporting import factcache_signals  # noqa: F401
