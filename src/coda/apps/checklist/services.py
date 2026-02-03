import importlib
from django.conf import settings

from coda.checks.checkfactory import CheckFactory


def get_checkfactory() -> CheckFactory:
    module_path = getattr(settings, "CODA_CHECKLIST_FACTORY")
    module = importlib.import_module(module_path)
    factory = getattr(module, "checkfactory", None)
    assert isinstance(factory, CheckFactory), (
        f"Expected {module_path}.checkfactory to be an instance of CheckFactory"
    )
    return factory
