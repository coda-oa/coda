# Choose a production-safe DaisyUI CSS delivery path

Status: resolved
Type: research

## Question

Given this repo has no frontend build dependency declared in `pyproject.toml`, serves app assets through Django staticfiles and WhiteNoise, renders DaisyUI classes from Django templates and HTMX fragments, and has custom elements with Shadow DOM, what supported Tailwind + daisyUI integration should produce and serve the CSS? Research current official documentation; recommend build/runtime placement, template class scanning (including dynamic class construction), static asset output/collection, and how CSS reaches the custom elements. Include primary-source links and concrete compatibility risks; do not change the repository.

## Answer

Use the official Tailwind standalone CLI with daisyUI's standalone plugin bundle; compile in a controlled build stage and emit the generated CSS under Django's static source before `collectstatic`. Keep build-only inputs outside that static tree and load the output via Django's `{% static %}` tag. Explicitly scan every Django template and HTMX partial; Tailwind does not execute templates, so use complete class literals or an explicit finite source list rather than interpolating class fragments. **Shadow DOM correction:** both search-select components currently define their own shadow-local CSS. A generic `addGlobalStylesToShadowRoot` helper exists but has no application call sites; using it for generated DaisyUI CSS requires explicit wiring. Keep document-side `::part` rules, and review Tailwind v4 browser support and Preflight.

Sources and trade-offs: [daisyUI Django install](https://daisyui.com/docs/install/django/), [Tailwind source detection](https://tailwindcss.com/docs/detecting-classes-in-source-files), [Django static files](https://docs.djangoproject.com/en/6.1/howto/static-files/), [WhiteNoise Django guide](https://whitenoise.readthedocs.io/en/stable/django.html). Full report: [DaisyUI CSS delivery research](file:///tmp/coda-daisyui-css-delivery/.scratch/daisyui-django-template-migration/research/01-daisyui-css-delivery.md) — branch `research/daisyui-css-delivery`, commit `aad7b667`.