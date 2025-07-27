from typing import Any

from django import template
from django.template import Context

from coda.apps.htmx_components.forms import (
    FormType,
    HtmxDynamicFormset,
    HxVals,
    render_formset_to_string,
)

register = template.Library()


@register.simple_tag(takes_context=True)
def render_formset(
    context: Context,
    formset: HtmxDynamicFormset[FormType],
    mode: str = "inline",
    hx_include: str = "",
    **kwargs: Any,
) -> str:
    """
    Render an HTMX dynamic formset with optional keyword arguments.

    Usage:
        {% load formset_tags %}
        {% render_formset contract_formset %}
        {% render_formset contract_formset mode="paragraph" %}
        {% render_formset contract_formset mode="inline" hx_include="#some-element" %}
        {% render_formset contract_formset mode="div" custom_class="my-class" show_header=True %}

    Args:
        context: The template context (automatically passed by Django)
        formset: The HtmxDynamicFormset instance to render
        mode: The rendering mode ("inline", "paragraph", "div")
        **kwargs: Additional keyword arguments passed to the formset's render method

    Returns:
        Rendered HTML string
    """
    if not isinstance(formset, HtmxDynamicFormset):
        raise template.TemplateSyntaxError(
            f"render_formset expects an HtmxDynamicFormset instance, got {type(formset)}"
        )

    request = context.get("request")

    hx_vals = HxVals(
        prefix=formset.prefix,
        mode=mode,
        hx_include=hx_include,
        extras=kwargs,
    )

    return render_formset_to_string(
        formset.template_name,
        formset.prerender_forms(formset.forms, request.POST if request else None),
        formset.name,
        formset.form_id,
        formset.add_button,
        formset.table_classes,
        hx_vals,
        request=request,
    )
