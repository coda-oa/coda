from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

from coda.apps.exports.models import ContractCSVExport, FundingRequestCSVExport


@receiver(post_delete, sender=FundingRequestCSVExport)
def delete_csv_file_on_export_delete(
    sender: type[FundingRequestCSVExport], instance: FundingRequestCSVExport, **kwargs: Any
) -> None:
    if instance.csv_file:
        instance.csv_file.delete(save=False)


@receiver(post_delete, sender=ContractCSVExport)
def delete_csv_file_on_contract_export_delete(
    sender: type[ContractCSVExport], instance: ContractCSVExport, **kwargs: Any
) -> None:
    if instance.csv_file:
        instance.csv_file.delete(save=False)
