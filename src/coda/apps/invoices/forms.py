from django import forms

from coda.apps.publishers.models import Publisher


class InvoiceForm(forms.Form):
    number = forms.CharField(max_length=255)
    recipient = forms.ModelChoiceField(queryset=Publisher.objects.all())
