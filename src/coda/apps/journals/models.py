from django.db import models


class Publisher(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Journal(models.Model):
    title = models.CharField(max_length=255)
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name="journals")
    eissn = models.CharField(max_length=9)
    open_access_type = models.CharField(max_length=255)
    successor_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, related_name="predecessor", null=True
    )
    licenses = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
