from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from coda.apps.breadcrumbs.decorators import breadcrumb, generate_dynamic_title
from coda.apps.contracts.models import Contract
from coda.apps.invoices import invoice_query as iq
from coda.apps.invoices import repository
from coda.apps.invoices.mappers import InvoiceDetailMapper
from coda.apps.invoices.mappers._domain import InvoiceDomainMapper
from coda.apps.invoices.models import FundingSource
from coda.apps.invoices.models import Invoice as InvoiceModel
from coda.apps.invoices.views.position_context import DefaultContext as _DefaultContext
from coda.apps.invoices.views.position_context import (
    funding_source_options_context,
    institutions_context,
)
from coda.apps.listfilters import (
    ChipBuilder,
    FilterSummary,
    ListRegionMixin,
    parse_date_filter,
)
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.views import EntityListView
from coda.contexts.finance.dto.edit_position_dtos import DEFAULT_TAX_RATE_PERCENTAGE
from coda.contexts.finance.services import invoice_service
from coda.domain.finance.invoice import (
    FundingSourceId,
    Invoice,
    InvoiceId,
    PaymentStatus,
    UnassignedCosts,
)
from coda.domain.invoice_list_item import InvoiceListItem
from coda.domain.money import Currency

_DATE_START_KEY = "date_start"
_DATE_END_KEY = "date_end"


def _contract_year_criterion(param: str, request: HttpRequest) -> iq.InvoiceSearchCriterion | None:
    try:
        year = int(param)
    except ValueError:
        return None
    return iq.ContractYearCriterion(year, request.GET.get("contract_positions_only") == "true")


_query_params_to_criteria: dict[
    str, Callable[[str, HttpRequest], iq.InvoiceSearchCriterion | None]
] = {
    "search_term": lambda param, _: iq.GenericSearchCriterion(param),
    "funding_source": lambda param, _: iq.FundingSourceCriterion(FundingSourceId(int(param))),
    "contract_name": lambda param, request: iq.ContractCriterion(
        param, request.GET.get("contract_positions_only") == "true"
    ),
    "contract_year": _contract_year_criterion,
    "has_external_id": lambda *_: iq.MissingExternalIdCriterion(),
    "has_foreign_currency": lambda *_: iq.MissingCurrencyConversionCriterion(
        GlobalPreferences.get_home_currency()
    ),
    "has_errors": lambda *_: iq.HasErrorsCriterion(),
    "payment_status": lambda param, _: iq.PaymentStatusCriterion(PaymentStatus(param)),
}


def build_query(request: HttpRequest) -> list[iq.InvoiceSearchCriterion]:
    query = []
    for param_name, get_query in _query_params_to_criteria.items():
        if param := request.GET.get(param_name):
            criterion = get_query(param, request)
            if criterion is not None:
                query.append(criterion)

    date_filter = parse_date_filter(request, start_key=_DATE_START_KEY, end_key=_DATE_END_KEY)
    if date_filter.date_range is not None:
        query.append(iq.DateRangeCriterion(date_filter.date_range))

    return query


def build_filter_summary(
    request: HttpRequest,
    contracts: Sequence[Contract],
    funding_sources: Iterable[FundingSource],
) -> FilterSummary:
    """One removable chip per active filter, in the sidebar's group order.

    Unknown ids (stale URLs) fall back to the raw value.
    """
    chips = ChipBuilder(
        request, list_url_name="invoices:list", region_url_name="invoices:list_region"
    )
    chips.single("payment_status")
    chips.single(
        "funding_source",
        labels={str(source.pk): source.name for source in funding_sources},
    )
    chips.single(
        "contract_name",
        labels={str(contract.pk): contract.name for contract in contracts},
    )
    chips.single("contract_year", prefix="Year ")
    chips.date_range(
        start_key=_DATE_START_KEY,
        end_key=_DATE_END_KEY,
        start_source_id=_DATE_START_KEY,
        end_source_id=_DATE_END_KEY,
    )
    chips.switch("has_external_id", "Without external ID")
    chips.switch("has_foreign_currency", "Foreign currency")
    chips.switch("has_errors", "With errors")
    return chips.summary()


def get_contract_list_context() -> dict[str, Any]:
    return {"contract_list": Contract.objects.all()}


@breadcrumb("Invoices", parent_url_name="invoices:finances_home")
class _InvoiceListBaseView(LoginRequiredMixin, EntityListView[InvoiceListItem]):
    paginate_by = 20
    entity_name = "Invoices"
    entity_list_item_template = "invoices/invoice_list_item.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["payment_statuses"] = [p.value for p in PaymentStatus]
        ctx.update(funding_source_options_context())
        ctx["home_currency"] = GlobalPreferences.get_home_currency()
        ctx.update(get_contract_list_context())
        summary = build_filter_summary(self.request, ctx["contract_list"], ctx["funding_sources"])
        ctx["active_filters"] = summary.chips
        ctx["filter_count"] = summary.count
        ctx["filter_errors"] = summary.errors
        ctx["date_filter_error"] = summary.error_for(_DATE_START_KEY, _DATE_END_KEY)
        return ctx

    def get_entities(self, request: HttpRequest) -> Sequence[InvoiceListItem]:
        sort_by = request.GET.get("sort_by") or "date_desc"
        return iq.search_to_list_items(*build_query(request), sort_by=sort_by)


class InvoiceListView(_InvoiceListBaseView):
    template_name = "invoices/invoice_list.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | institutions_context()


class InvoiceListRegionView(ListRegionMixin, _InvoiceListBaseView):
    template_name = "invoices/invoice_filtered_list.html"
    region_url_name = "invoices:list"


invoice_list = InvoiceListView.as_view()
invoice_list_region = InvoiceListRegionView.as_view()


@dataclass
class _InvoiceNumber:
    id: int | str
    number: str


invoice_breadcrumb_title = generate_dynamic_title(
    model_name="Invoice",
    fetch_fn=lambda pk: _InvoiceNumber(pk, repository.invoice_number_of(InvoiceId(int(pk)))),
    label_attr="number",
    fallback_attr="id",
    default_title="Invoice Details",
)


@login_required
@require_GET
@breadcrumb(invoice_breadcrumb_title, parent_url_name="invoices:list", preserve_filters=True)
def invoice_detail(request: HttpRequest, pk: int) -> HttpResponse:
    model = InvoiceDetailMapper.prefetch(InvoiceModel.objects.all()).get(pk=pk)
    invoice = InvoiceDomainMapper.map(model)
    base_vm = InvoiceDetailMapper.map(model)
    display_currency = Currency.from_code(
        request.GET.get("display_currency", invoice.currency().code)
    )
    display_invoice = invoice.convert(display_currency)
    display_vm = base_vm.with_conversion(display_invoice)
    editable = False
    return render(
        request,
        "invoices/detail.html",
        _DefaultContext
        | funding_source_options_context()
        | {
            "invoice": base_vm,
            "conversions": invoice.conversions(),
            "display_currency": display_currency,
            "display_invoice": display_vm,
            "editable": editable,
        },
    )


@login_required
@require_GET
def load_conversion_section(request: HttpRequest) -> HttpResponse:
    selected_currency = request.GET.get("currency")
    home_currency = GlobalPreferences.get_home_currency().code

    invoice = None
    conversions = {}

    invoice_id = request.GET.get("invoice_id", "").strip()
    if invoice_id:
        invoice = repository.get_by_id(InvoiceId(int(invoice_id)))
        conversions = invoice.conversions()

    if selected_currency == home_currency and (not invoice or not invoice.conversions()):
        return HttpResponse("")

    return render(
        request,
        "invoices/detail_conversions.html",
        {
            "selected_currency": selected_currency,
            "home_currency": home_currency,
            "conversions": conversions,
        },
    )


@login_required
@require_POST
def pay_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    if request.POST.get("action") == "pay":
        _try_pay(invoice, request)
    elif request.POST.get("action") == "reset_payment":
        invoice.reset_payment()
    invoice_service.save(invoice)
    return redirect("invoices:detail", pk=invoice.id)


def _try_pay(invoice: Invoice, request: HttpRequest) -> None:
    try:
        invoice.pay()
    except UnassignedCosts:
        messages.error(request, "Invoice has unassigned costs")


@require_GET
@login_required
def position_cost_type_options(request: HttpRequest) -> HttpResponse:
    counter = request.GET.get("counter")
    cost_type_key = f"positions-{counter}-item-cost_type"
    cost_type = request.GET.get(cost_type_key)
    if cost_type == "vat":
        return HttpResponse("")

    tax_rate_key = f"positions-{counter}-tax_rate"
    tax_rate = request.GET.get(tax_rate_key, DEFAULT_TAX_RATE_PERCENTAGE)

    return render(
        request,
        "invoices/position_tax_rate.html",
        {"counter": counter, "tax_rate": tax_rate},
    )
