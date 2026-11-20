from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.html import format_html
from django.views.decorators.http import require_GET, require_POST
from django_htmx.http import HttpResponseClientRedirect

from coda.apps.breadcrumbs.decorators import breadcrumb, generate_dynamic_title
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.queries import detail
from coda.contexts.fundingrequest.services import fundingrequests as fr_services
from coda.domain.fundingrequest import FundingRequestId

template_name = "fundingrequests/fundingrequest_detail.html"


@dataclass(frozen=True)
class _DummyRequestIdWrapper:
    """This is just a wrapper because breadcrumbs currently work by attribute"""

    name: str


funding_request_breadcrumb_title = generate_dynamic_title(
    model_name="Funding Request",
    fetch_fn=lambda pk: _DummyRequestIdWrapper(
        str(repository.get_request_id_for(FundingRequestId(int(pk))))
    ),
    fallback_attr="id",
    default_title="Funding Request Details",
)


@login_required
@breadcrumb(
    funding_request_breadcrumb_title, parent_url_name="fundingrequests:list", preserve_filters=True
)
def fundingrequest_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Funding request detail view.

    Delegates to query service for data fetching and transformation.
    """
    context = detail.get_detail_context(FundingRequestId(pk))
    return render(request, template_name, context)


@login_required
@require_GET
def request_delete_fundingrequest(request: HttpRequest, pk: int) -> HttpResponse:
    fundingrequest = get_object_or_404(FundingRequestModel, pk=pk)
    can_delete, blocking = fr_services.can_delete_fundingrequest(FundingRequestId(pk))
    blocking_reasons = [
        format_html('<a href="{}">{}</a>', ref.url, ref.description) if ref.url else ref.description
        for ref in blocking
    ]

    return render(
        request,
        "partials/entity_deletion_modal.html",
        {
            "entity_type": "Funding Request",
            "entity_name": str(fundingrequest.request_id),
            "can_delete": can_delete,
            "blocking_reasons": blocking_reasons,
            "reason_intro": "Cannot delete this funding request, it is referenced by:",
            "delete_url": reverse("fundingrequests:fundingrequest_delete", kwargs={"pk": pk}),
        },
    )


@login_required
@require_POST
def delete_fundingrequest(request: HttpRequest, pk: int) -> HttpResponse:
    fundingrequest = get_object_or_404(FundingRequestModel, pk=pk)
    can_delete, blocking = fr_services.can_delete_fundingrequest(FundingRequestId(pk))

    if not can_delete:
        reasons = ", ".join(ref.description for ref in blocking)
        messages.error(request, f"Cannot delete funding request, it is referenced by: {reasons}")
        return HttpResponseClientRedirect(reverse("fundingrequests:detail", kwargs={"pk": pk}))

    request_id = str(fundingrequest.request_id)
    try:
        fr_services.delete_fundingrequest(FundingRequestId(pk))
    except ValueError as exc:
        messages.error(request, str(exc))
        return HttpResponseClientRedirect(reverse("fundingrequests:detail", kwargs={"pk": pk}))
    except FundingRequestModel.DoesNotExist:
        messages.error(request, f"Funding request '{request_id}' was already deleted.")
        return HttpResponseClientRedirect(reverse("fundingrequests:list"))
    messages.success(request, f"Funding request '{request_id}' deleted.")

    return HttpResponseClientRedirect(reverse("fundingrequests:list"))
