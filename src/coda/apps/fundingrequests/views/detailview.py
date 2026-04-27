from dataclasses import dataclass
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.breadcrumbs.decorators import breadcrumb, generate_dynamic_title
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.queries import detail
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
