from coda.apps.blocklist.models import BlockList
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.checks.checklist import CheckFailed, CheckResult, CheckSuccessful
from coda.fundingrequest import FundingRequest, TPublication
from coda.publication import Monograph, Publication


class BlockCheck:
    params: dict[str, str | int] = {}

    @property
    def name(self) -> str:
        return self.description

    @property
    def description(self) -> str:
        return "Check if a publisher or journal is on the blocklist."

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        blocklist = BlockList.objects.get()
        if isinstance(fundingrequest.publication, Publication):
            journal = Journal.objects.get(pk=fundingrequest.publication.journal)
            publisher = journal.publisher

            journal_blocked = blocklist.is_journal_blocked(journal)
            publisher_blocked = blocklist.is_publisher_blocked(publisher)
            if journal_blocked or publisher_blocked:
                return CheckFailed(reason="Journal or publisher is on the blocklist")

        elif isinstance(fundingrequest.publication, Monograph):
            publisher_id = fundingrequest.publication.publisher
            publisher = Publisher.objects.get(pk=publisher_id)
            publisher_blocked = blocklist.is_publisher_blocked(publisher)
            if publisher_blocked:
                return CheckFailed(reason="Publisher is on the blocklist")

        return CheckSuccessful()
