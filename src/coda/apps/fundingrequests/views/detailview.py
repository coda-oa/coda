from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.breadcrumbs.decorators import breadcrumb, generate_dynamic_title
from coda.apps.fundingrequests import repository
from coda.apps.fundingrequests.queries import detail
from coda.domain.fundingrequest import FundingRequestId

template_name = "fundingrequests/fundingrequest_detail.html"


funding_request_breadcrumb_title = generate_dynamic_title(
    model_name="Funding Request",
    fetch_fn=lambda pk: repository.get_by_id(FundingRequestId(int(pk))),
    label_attr="request_id",
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
