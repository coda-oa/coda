from django.db import models

from coda.apps.fundingrequests.models import FundingRequest


class CheckRun(models.Model):
    check_name = models.CharField(max_length=255)
    check_parameters = models.JSONField(default=dict)
    fundingrequest = models.ForeignKey(FundingRequest, on_delete=models.CASCADE)

    message = models.TextField(blank=True)
    result = models.CharField(max_length=255)
    result_data = models.JSONField(default=dict)

    timestamp = models.DateTimeField()
