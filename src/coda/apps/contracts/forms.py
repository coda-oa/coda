from django import forms

from coda.apps.htmx_components.forms import HtmxDynamicFormset


class ContractForm(forms.Form):
    use_required_attribute = False
    name = forms.CharField(required=True)
    start_date = forms.DateField(required=False, widget=forms.TextInput(attrs={"type": "date"}))
    end_date = forms.DateField(required=False, widget=forms.TextInput(attrs={"type": "date"}))


class EntityForm(forms.Form):
    use_required_attribute = False
    name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"readonly": True}),
    )
    entity_id = forms.IntegerField(widget=forms.HiddenInput())


class EntityFormset(HtmxDynamicFormset[EntityForm]):
    form_class = EntityForm
    name = "contracts:entity-formset"
    add_button = False
    min_forms = 0

    table_classes = "article__table"
