from datetime import timedelta

import pytest
from django.utils import timezone

from coda.apps.blocklist.models import BlockList
from tests import modelfactory


@pytest.mark.django_db
def test__can_only_create_one_blocklist() -> None:
    blocklist_1 = BlockList.objects.create()
    assert BlockList.objects.count() == 1

    blocklist_2 = BlockList.objects.create()
    assert BlockList.objects.count() == 1

    blocklist_3 = BlockList()
    blocklist_3.save()
    assert BlockList.objects.count() == 1

    assert blocklist_1 == blocklist_2 == blocklist_3


@pytest.mark.django_db
def test__a_blocked_journal_needs_to_be_reviewed_after_six_months() -> None:
    six_months_ago = timezone.now() - timedelta(days=31 * 6)
    four_months_ago = timezone.now() - timedelta(days=31 * 4)

    blocklist = BlockList.objects.create()
    blocklist.block_journal(journal=modelfactory.journal(), reason="MIRROR", now=six_months_ago)
    blocklist.block_journal(journal=modelfactory.journal(), reason="PREDATORY", now=four_months_ago)

    now = timezone.now()
    blocklist.journals_to_review(now).count() == 1


@pytest.mark.django_db
def test__a_journal_up_for_review__when_confirming_block__is_no_longer_up_for_review() -> None:
    six_months_ago = timezone.now() - timedelta(days=31 * 6)
    blocklist = BlockList.objects.create()
    journal = modelfactory.journal()
    blocklist.block_journal(journal=journal, reason="MIRROR", now=six_months_ago)

    now = timezone.now()
    blocklist.confirm_journal_block(journal, now)

    assert blocklist.journals_to_review(now).count() == 0


@pytest.mark.django_db
def test__blocking_journal_for_different_reason__updates_reason() -> None:
    blocklist = BlockList.objects.create()
    journal = modelfactory.journal()

    blocklist.block_journal(journal=journal, reason="MIRROR")
    blocklist.block_journal(journal=journal, reason="PREDATORY")

    assert blocklist.blocked_journals().get().reason == "PREDATORY"


@pytest.mark.django_db
def test__unblocking_journal__removes_journal_from_blocklist() -> None:
    blocklist = BlockList.objects.create()
    journal = modelfactory.journal()

    blocklist.block_journal(journal=journal, reason="MIRROR")
    blocklist.unblock_journal(journal)

    assert blocklist.blocked_journals().count() == 0
