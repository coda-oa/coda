from django.template import Template, Context


def test__update_banner__renders_when_update_available() -> None:
    template = Template(
        "{% if update_available %}" '<div class="update-banner">update!</div>' "{% endif %}"
    )
    rendered = template.render(Context({"update_available": True}))
    assert "update!" in rendered


def test__update_banner__not_rendered_when_no_update() -> None:
    template = Template(
        "{% if update_available %}" '<div class="update-banner">update!</div>' "{% endif %}"
    )
    rendered = template.render(Context({"update_available": False}))
    assert "update!" not in rendered
