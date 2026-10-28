from django.apps import AppConfig


class PointageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pointage"
    verbose_name = "Gestion de présence"

    def ready(self):
        from . import signals  # noqa: F401
