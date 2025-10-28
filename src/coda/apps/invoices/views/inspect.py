import datetime
from decimal import Decimal
from typing import Any, NamedTuple, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from coda.apps.breadcrumbs.decorators import breadcrumb, generate_dynamic_title
from coda.apps.contracts.models import Contract
from coda.apps.invoices import repository
from coda.apps.invoices.models import Creditor
from coda.apps.invoices.views.position_list import _DefaultContext, funding_sources_context
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.views import EntityListView
from coda.contexts.finance.dto.detail_position_dtos import PositionDetailDto
from coda.contexts.finance.dto.edit_position_dtos import DEFAULT_TAX_RATE_PERCENTAGE
from coda.contexts.finance.services import invoice_service
from coda.domain.date import DateRange
from coda.domain.finance.invoice import Invoice, InvoiceId, PaymentStatus
from coda.domain.invoice_list_item import InvoiceListItem
from coda.domain.money import Money
from coda.domain.money._currency import Currency

_advanced_search_fields = [
    "payment_status",
    "date_start",
    "date_end",
    "funding_source",
    "has_external_id",
    "has_foreign_currency",
    "contract_name",
    "contract_year",
]


def get_contract_list_context() -> dict[str, Any]:
    return {"contract_list": Contract.objects.all()}


@breadcrumb("Invoices", parent_url_name="invoices:finances_home")
class InvoiceListView(LoginRequiredMixin, EntityListView[InvoiceListItem]):
    paginate_by = 20
    entity_name = "Invoices"
    template_name = "invoices/invoice_list.html"
    entity_list_item_template = "invoices/invoice_list_item.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["payment_statuses"] = [p.value for p in PaymentStatus]
        ctx.update(funding_sources_context())
        ctx["home_currency"] = GlobalPreferences.get_home_currency()
        ctx["expand_advanced_search"] = any(
            self.request.GET.get(key) for key in _advanced_search_fields
        )
        ctx.update(get_contract_list_context())

        return ctx

    def get_entities(self, request: HttpRequest) -> list[InvoiceListItem]:
        query: dict[str, Any] = {
            "generic_search": request.GET.get("search_term"),
            "funding_source": request.GET.get("funding_source") or None,
            "contract_id": request.GET.get("contract_name") or None,
            "contract_year": request.GET.get("contract_year") or None,
            "home_currency": GlobalPreferences.get_home_currency(),
            "has_external_id": self.bool_like(request.GET.get("has_external_id")),
            "has_foreign_currency": self.bool_like(request.GET.get("has_foreign_currency")),
            "sort_by": request.GET.get("sort_by"),
            "status": self.try_into_paymentstatus(request.GET.get("payment_status", "")),
            "date_range": DateRange.try_fromisoformat(
                start=request.GET.get("date_start"),
                end=request.GET.get("date_end"),
            ),
        }

        return list(repository.search(**query))

    def try_into_paymentstatus(self, status: str) -> PaymentStatus | None:
        try:
            return PaymentStatus(status)
        except ValueError:
            return None

    def bool_like(self, value: str | None) -> bool | None:
        if not value:
            return None

        return value.lower() == "true"


invoice_list = InvoiceListView.as_view()


invoice_breadcrumb_title = generate_dynamic_title(
    model_name="Invoice",
    fetch_fn=lambda pk: repository.get_by_id(InvoiceId(int(pk))),
    label_attr="number",
    fallback_attr="id",
    default_title="Invoice Details",
)


@login_required
@require_GET
@breadcrumb(invoice_breadcrumb_title, parent_url_name="invoices:list", preserve_filters=True)
def invoice_detail(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    display_currency = Currency.from_code(
        request.GET.get("display_currency", invoice.currency().code)
    )
    display_invoice = invoice.convert(display_currency)
    editable = False
    return render(
        request,
        "invoices/detail.html",
        _DefaultContext
        | funding_sources_context()
        | {
            "invoice": invoice_viewmodel(invoice),
            "conversions": invoice.conversions(),
            "display_currency": display_currency,
            "display_invoice": invoice_viewmodel(display_invoice),
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


def invoice_viewmodel(invoice: Invoice) -> "InvoiceViewModel":
    creditor_name = Creditor.objects.get(id=invoice.creditor).name
    id = cast(InvoiceId, invoice.id)
    url = reverse("invoices:detail", kwargs={"pk": id})

    return InvoiceViewModel(
        id=id,
        url=url,
        status=invoice.status.name,
        number=invoice.number,
        date=invoice.date,
        creditor=invoice.creditor,
        creditor_name=creditor_name,
        currency=invoice.currency(),
        positions=[PositionDetailDto.to_position_detail_dto(p) for p in invoice.positions],
        tax=invoice.tax(),
        total=invoice.total(),
        net=invoice.net(),
        comment=invoice.comment,
        external_invoice_id=invoice.external_invoice_id,
        conversions=invoice.conversions(),
    )


@login_required
@require_POST
def pay_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    if request.POST.get("action") == "pay":
        invoice.pay()
    elif request.POST.get("action") == "reset_payment":
        invoice.reset_payment()
    invoice_service.save(invoice)
    return redirect("invoices:detail", pk=invoice.id)


@require_GET
@login_required
def position_cost_type_options(request: HttpRequest) -> HttpResponse:
    counter = request.GET.get("counter")
    cost_type_key = f"positions-{counter}-cost_type"
    cost_type = request.GET.get(cost_type_key)
    if cost_type == "vat":
        return HttpResponse("")
    return render(
        request,
        "invoices/position_tax_rate.html",
        {"counter": counter, "tax_rate": DEFAULT_TAX_RATE_PERCENTAGE},
    )


class InvoiceViewModel(NamedTuple):
    id: int
    url: str
    status: str
    number: str
    date: datetime.date
    creditor: int
    creditor_name: str
    currency: Currency
    positions: list[PositionDetailDto]
    tax: Money
    total: Money
    net: Money
    comment: str
    external_invoice_id: str
    conversions: dict[Currency, Decimal]
