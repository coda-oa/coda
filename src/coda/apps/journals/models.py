from django.db import models


class Publisher(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Journal(models.Model):
    title = models.CharField(max_length=255)
    eissn = models.CharField(max_length=9)
    licenses = models.CharField(max_length=255, null=True)
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name="journals")
    open_access_type = models.CharField(max_length=255, null=True)
    successor_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, related_name="predecessor", null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
