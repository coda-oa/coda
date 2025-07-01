from coda.apps.fundingrequests.forms import ExtraContactForm
from coda.apps.fundingrequests.views.wizard.formrestore import restore_form
from coda.apps.wizard import FormStep, Store


from django.http import HttpRequest


from typing import Any


class ExtraInformationStep(FormStep):
    template_name: str = "fundingrequests/fundingrequest_submitter.html"
    form_class = ExtraContactForm

    def get_context_data(self, request: HttpRequest, store: Store) -> dict[str, Any]:
        return super().get_context_data(request, store) | {
            "form": restore_form(self.form_class, request, store.get("contact")),
            "request_remarks": self.restore_remarks(request, store),
        }

    def restore_remarks(self, request: HttpRequest, store: Store) -> str:
        if posted_remarks := request.POST.get("request_remarks"):
            return posted_remarks

        return str(store.get("request_remarks", ""))

    def is_valid(self, request: HttpRequest, store: Store) -> bool:
        form = ExtraContactForm(request.POST)
        valid = form.is_valid()
        return valid

    def done(self, request: HttpRequest, store: Store) -> None:
        form = ExtraContactForm(request.POST)
        form.full_clean()
        if form.has_changed():
            store["contact"] = form.to_dto()
        elif "contact" in store:
            del store["contact"]

        store["request_remarks"] = request.POST.get("request_remarks", "")
        store.save()
