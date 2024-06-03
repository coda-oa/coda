from django import forms

from coda.apps.publishers.models import Publisher


class InvoiceForm(forms.Form):
    use_required_attribute = False
    number = forms.CharField(max_length=255, label="Invoice Number")
    date = forms.DateField(label="Invoice Date")
    creditor = forms.ModelChoiceField(queryset=Publisher.objects.all())
