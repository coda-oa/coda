from django.template import Template, Context


def test_update_banner_RendersWhenUpdateAvailable() -> None:
    template = Template(
        "{% if update_available %}" '<div class="update-banner">update!</div>' "{% endif %}"
    )
    rendered = template.render(Context({"update_available": True}))
    assert "update!" in rendered


def test_update_banner_NotRenderedWhenNoUpdate() -> None:
    template = Template(
        "{% if update_available %}" '<div class="update-banner">update!</div>' "{% endif %}"
    )
    rendered = template.render(Context({"update_available": False}))
    assert "update!" not in rendered
