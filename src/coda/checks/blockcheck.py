from coda.apps.blocklist.models import BlockList
from coda.apps.journals.models import Journal
from coda.apps.publishers.models import Publisher
from coda.checks.checklist import CheckFailed, CheckResult, CheckSuccessful, CheckWarning
from coda.domain.fundingrequest import FundingRequest, TPublication
from coda.domain.publication import Monograph, Publication


class BlockCheck:
    params: dict[str, str | int] = {}

    @property
    def name(self) -> str:
        return "Blocklist Check"

    @property
    def description(self) -> str:
        return "Check if a publisher or journal is on the blocklist."

    def __call__(self, fundingrequest: FundingRequest[TPublication]) -> CheckResult:
        blocklist = BlockList.objects.get()
        if isinstance(fundingrequest.publication, Publication):
            journal = Journal.objects.get(pk=fundingrequest.publication.journal)
            publisher = journal.publisher

            blocked_journal = blocklist.get_blocked_journal(journal)
            if blocked_journal:
                if blocked_journal.needs_review():
                    return self.journal_blocked_warning(journal)

                return self.journal_blocked_result(journal)

            publisher_blocked = blocklist.is_publisher_blocked(publisher)
            if publisher_blocked:
                return self.publisher_blocked_result(publisher)

            return CheckSuccessful(message="Journal and publisher are not on the blocklist")

        elif isinstance(fundingrequest.publication, Monograph):
            publisher_id = fundingrequest.publication.publisher
            publisher = Publisher.objects.get(pk=publisher_id)
            publisher_blocked = blocklist.is_publisher_blocked(publisher)
            if publisher_blocked:
                return self.publisher_blocked_result(publisher)

            return CheckSuccessful(message="Monograph publisher is not on the blocklist")

        else:
            raise ValueError("Invalid publication type")

    def journal_blocked_result(self, journal: Journal) -> CheckFailed:
        return CheckFailed(message=f'Journal "{journal.title}" is on the blocklist')

    def journal_blocked_warning(self, journal: Journal) -> CheckWarning:
        return CheckWarning(
            message=f'Journal "{journal.title}" is on the blocklist, but needs a review'
        )

    def publisher_blocked_result(self, publisher: Publisher) -> CheckFailed:
        return CheckFailed(message=f"Publisher {publisher.name} is on the blocklist")
