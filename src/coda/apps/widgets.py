from django import forms


class SearchSelectWidget(forms.Select):
    template_name = "forms/search-select-widget.html"
    option_template_name = "forms/search-select-option-widget.html"
