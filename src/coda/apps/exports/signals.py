from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver

from coda.apps.exports.models import ContractCSVExport, FundingRequestCSVExport


@receiver(post_delete, sender=FundingRequestCSVExport)
@receiver(post_delete, sender=ContractCSVExport)
def delete_csv_file_on_export_delete(sender: Any, instance: Any, **kwargs: Any) -> None:
    if instance.csv_file:
        instance.csv_file.delete(save=False)
