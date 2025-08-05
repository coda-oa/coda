import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, NamedTuple, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from coda.apps.contracts.models import Contract
from coda.apps.invoices import repository, services
from coda.apps.invoices.models import Creditor
from coda.apps.invoices.views.position_list import _DefaultContext
from coda.apps.invoices.views.position_list import funding_sources_context
from coda.apps.invoices.views.positions import AnyPositionDto, to_position_dto
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.views import EntityListView
from coda.domain.date import DateRange
from coda.domain.invoice import Invoice, InvoiceId, PaymentStatus
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


class InvoiceListView(LoginRequiredMixin, EntityListView["InvoiceViewModel"]):
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

    def get_entities(self, request: HttpRequest) -> Sequence["InvoiceViewModel"]:
        query: dict[str, Any] = {}
        query["generic_search"] = request.GET.get("search_term")

        if status := request.GET.get("payment_status"):
            query["status"] = self.try_into_paymentstatus(status)

        query["funding_source"] = request.GET.get("funding_source") or None

        query["contract_name"] = request.GET.get("contract_name") or None
        query["contract_year"] = request.GET.get("contract_year") or None

        query["date_range"] = DateRange.try_fromisoformat(
            start=request.GET.get("date_start"),
            end=request.GET.get("date_end"),
        )

        if (has_external_id := request.GET.get("has_external_id")) in ("true", "false"):
            query["has_external_id"] = has_external_id == "true"

        query["home_currency"] = GlobalPreferences.get_home_currency()
        if (has_foreign_currency := request.GET.get("has_foreign_currency")) in ("true", "false"):
            query["has_foreign_currency"] = has_foreign_currency == "true"

        query["sort_by"] = request.GET.get("sort_by")

        return list(invoice_viewmodel(i) for i in repository.search(**query))

    def try_into_paymentstatus(self, status: str) -> PaymentStatus | None:
        try:
            return PaymentStatus(status)
        except ValueError:
            return None


invoice_list = InvoiceListView.as_view()


@login_required
@require_GET
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
        positions=[to_position_dto(position) for position in invoice.positions],
        tax=invoice.tax(),
        total=invoice.total(),
        net=invoice.net(),
        comment=invoice.comment,
        external_invoice_id=invoice.external_invoice_id,
        conversion=invoice.conversions(),
    )


@login_required
@require_POST
def pay_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = repository.get_by_id(InvoiceId(pk))
    if request.POST.get("action") == "pay":
        invoice.pay()
    elif request.POST.get("action") == "reset_payment":
        invoice.reset_payment()
    services.save(invoice)
    return redirect("invoices:detail", pk=invoice.id)


class InvoiceViewModel(NamedTuple):
    id: int
    url: str
    status: str
    number: str
    date: datetime.date
    creditor: int
    creditor_name: str
    currency: Currency
    positions: list[AnyPositionDto]
    tax: Money
    total: Money
    net: Money
    comment: str
    external_invoice_id: str
    conversion: dict[Currency, Decimal]
