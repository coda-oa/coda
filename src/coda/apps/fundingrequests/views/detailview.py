from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from coda.apps.breadcrumbs.decorators import breadcrumb, generate_dynamic_title
from coda.apps.fundingrequests import detailview_mapper, repository
from coda.apps.fundingrequests.forms import ChooseLabelForm
from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.services import checks
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
    fr = FundingRequestModel.objects.get(pk=pk)
    return render(request, template_name, context(fr))


def context(fr: FundingRequestModel) -> dict[str, Any]:
    ctx = {
        "funding_request": detailview_mapper.to_funding_request_details(fr),
        "contact": fr.extra_contact,
        "publication": detailview_mapper.to_publication_details(fr),
        "label_form": ChooseLabelForm(),
        "external_funding": detailview_mapper.to_external_funding_list(fr.external_funding.all()),
        "checks": checks.get_checkrun(FundingRequestId(fr.id)),
    }

    return ctx
