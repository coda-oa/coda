from typing import Any

from django.contrib.auth.decorators import login_required
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from coda.apps.blocklist.models import (
    BlockedJournal,
    BlockedPublisher,
    BlockList,
    JournalBlockReason,
)
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher


@login_required
def blocklist(request: HttpRequest) -> HttpResponse:
    return render(request, "blocklist/blocklist_page.html", context("journals"))


@login_required
def tab_switch(request: HttpRequest) -> HttpResponse:
    tab = request.GET.get("tab", "journals")
    return render(request, "blocklist/blocklist.html", context(tab))


def context(tab: str) -> dict[str, Any]:
    blocklist = BlockList.objects.get()
    specific_ctx: dict[str, QuerySet[BlockedPublisher] | QuerySet[BlockedJournal]]
    if tab == "journals":
        specific_ctx = {"journals": blocklist.blocked_journals().all()}
    elif tab == "publishers":
        specific_ctx = {"publishers": blocklist.blocked_publishers().all()}
    else:
        raise Http404(f"Unknown tab {tab}")

    return {"tab": tab} | specific_ctx


@login_required
@require_GET
def request_block_journal(request: HttpRequest, pk: int) -> HttpResponse:
    journal = Journal.objects.get(pk=pk)
    return render(
        request,
        "blocklist/blocklist_block_journal_dialog.html",
        context={"journal": journal, "blockreasons": JournalBlockReason.choices},
    )


@login_required
@require_POST
def block_journal(request: HttpRequest, pk: int) -> HttpResponse:
    reason = request.POST.get("reason", "PREDATORY")
    journal = get_object_or_404(Journal, pk=pk)

    blocklist = BlockList.objects.get()
    blocklist.block_journal(journal, reason)

    return HttpResponse(
        headers={
            "HX-Redirect": reverse("publishing:journals:detail", kwargs={"eissn": journal.eissn})
        }
    )


@login_required
@require_POST
def unblock_journal(request: HttpRequest, pk: int) -> HttpResponse:
    journal = get_object_or_404(Journal, pk=pk)

    blocklist = BlockList.objects.get()
    blocklist.unblock_journal(journal)

    return maybe_redirect(request)


@login_required
@require_POST
def confirm_block(request: HttpRequest, pk: int) -> HttpResponse:
    journal = get_object_or_404(Journal, pk=pk)

    blocklist = BlockList.objects.get()
    blocklist.confirm_journal_block(journal)

    return HttpResponse()


@login_required
@require_GET
def request_block_publisher(request: HttpRequest, pk: int) -> HttpResponse:
    publisher = Publisher.objects.get(pk=pk)
    return render(
        request,
        "blocklist/blocklist_block_publisher_dialog.html",
        context={"publisher": publisher},
    )


@login_required
@require_POST
def block_publisher(request: HttpRequest, pk: int) -> HttpResponse:
    publisher = Publisher.objects.get(pk=pk)

    blocklist = BlockList.objects.get()
    blocklist.block_publisher(publisher)

    return HttpResponse(headers={"HX-Redirect": reverse("publishing:publishers:list")})


@login_required
@require_POST
def unblock_publisher(request: HttpRequest, pk: int) -> HttpResponse:
    publisher = Publisher.objects.get(pk=pk)

    blocklist = BlockList.objects.get()
    blocklist.unblock_publisher(publisher)

    return maybe_redirect(request)


def maybe_redirect(request: HttpRequest) -> HttpResponse:
    redirect_url = request.POST.get("redirect_url", "")
    if redirect_url:
        return HttpResponse(headers={"HX-Redirect": redirect_url})

    return HttpResponse()
