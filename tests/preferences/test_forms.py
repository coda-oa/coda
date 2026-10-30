from collections.abc import Iterable
from typing import TYPE_CHECKING, cast

import pytest
from django import forms
from django.forms import ModelChoiceField
from django.urls import reverse
from django.utils import timezone

from coda.apps.institutions.models import Institution
from coda.apps.preferences.forms import TOKEN_MASK, CrossrefAccessForm, GlobalPreferencesForm
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.widgets import SearchSelectWidget

if TYPE_CHECKING:
    from django.test import Client


def _crossref_post_data(**overrides: str) -> dict[str, str]:
    """POST data for the CrossrefAccessForm."""
    data = {
        "crossref_contact_email": "contact@example.org",
    }
    data.update(overrides)
    return data


def _verify_ok(token: str = "", pool: str = "plus-array") -> tuple[int, dict[str, str]]:
    return 200, {"x-api-pool": pool, "x-rate-limit-limit": "150", "x-rate-limit-interval": "1s"}


def _verify_rejected(token: str = "") -> tuple[int, dict[str, str]]:
    return 401, {}


def _verify_unreachable(token: str = "") -> tuple[int | None, dict[str, str]]:
    return None, {}


def _existing_prefs() -> "GlobalPreferences":
    """The singleton preferences row, so forms update instead of inserting."""
    prefs, _ = GlobalPreferences.objects.get_or_create()
    return prefs


@pytest.mark.django_db
def test__global_preferences_home_institution_dropdown__excludes_archived_institutions() -> None:
    active_institution = Institution.objects.create(name="Active University")
    archived_institution = Institution.objects.create(
        name="Archived University", archived_at=timezone.now()
    )

    form = GlobalPreferencesForm()
    home_institution_field = form.fields["home_institution"]
    assert isinstance(home_institution_field, ModelChoiceField)
    home_institution_queryset = home_institution_field.queryset
    assert home_institution_queryset is not None

    assert active_institution in home_institution_queryset
    assert archived_institution not in home_institution_queryset


def test__home_currency_field__offers_named_currency_choices() -> None:
    form = GlobalPreferencesForm()
    home_currency_field = form.fields["home_currency"]
    assert isinstance(home_currency_field, forms.ChoiceField)
    assert isinstance(home_currency_field.widget, SearchSelectWidget)
    assert ("EUR", "EUR - Euro") in list(
        cast("Iterable[tuple[str, str]]", home_currency_field.choices)
    )


@pytest.mark.django_db
def test__home_currency_field__rejects_unknown_currency_code() -> None:
    form = GlobalPreferencesForm(data={"home_currency": "NOTACURRENCY"})
    assert not form.is_valid()
    assert "home_currency" in form.errors


# --- Crossref politeness -----------------------------------------------------


@pytest.mark.django_db
def test__crossref_token__without_email__rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> tuple[int | None, dict[str, str]]:
        raise AssertionError("email check must short-circuit before verification")

    monkeypatch.setattr("coda.apps.preferences.forms.crossref_access.verify_plus_token", fail)
    form = CrossrefAccessForm(
        data=_crossref_post_data(crossref_contact_email="", crossref_plus_api_token="some-token"),
        instance=_existing_prefs(),
    )
    assert not form.is_valid()
    assert "crossref_contact_email" in form.errors


@pytest.mark.django_db
def test__crossref_token__posting_mask__keeps_stored_token_without_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mask round-trips the stored token; keeping it never re-verifies."""
    monkeypatch.setattr(
        "coda.apps.preferences.forms.crossref_access.verify_plus_token",
        _verify_ok,
    )
    prefs_form = CrossrefAccessForm(
        instance=_existing_prefs(),
        data=_crossref_post_data(crossref_plus_api_token="stored-token"),
    )
    assert prefs_form.is_valid(), prefs_form.errors
    prefs_form.save()

    def fail(*args: object, **kwargs: object) -> tuple[int | None, dict[str, str]]:
        raise AssertionError("keeping the stored token must not verify against Crossref")

    monkeypatch.setattr("coda.apps.preferences.forms.crossref_access.verify_plus_token", fail)

    update = CrossrefAccessForm(
        instance=_existing_prefs(),
        data=_crossref_post_data(crossref_plus_api_token=TOKEN_MASK),
    )
    assert update.is_valid(), update.errors
    update.save()

    saved = GlobalPreferences.objects.get()
    assert saved.crossref_plus_api_token == "stored-token"


@pytest.mark.django_db
def test__crossref_token__empty_field__removes_stored_token_without_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "expired-token"
    prefs.save()

    def fail(*args: object, **kwargs: object) -> tuple[int | None, dict[str, str]]:
        raise AssertionError("removal must not verify against Crossref")

    monkeypatch.setattr("coda.apps.preferences.forms.crossref_access.verify_plus_token", fail)

    update = CrossrefAccessForm(
        instance=prefs,
        data=_crossref_post_data(crossref_plus_api_token=""),
    )
    assert update.is_valid(), update.errors
    update.save()

    saved = GlobalPreferences.objects.get()
    assert saved.crossref_plus_api_token == ""
    # No key, no verdict.
    assert saved.crossref_plus_api_token_valid is None


@pytest.mark.django_db
def test__crossref_token__saving_verifies_new_token_before_persisting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def record(token: str, timeout: int = 5) -> tuple[int, dict[str, str]]:
        calls.append(token)
        return _verify_ok(token)

    monkeypatch.setattr("coda.apps.preferences.forms.crossref_access.verify_plus_token", record)
    form = CrossrefAccessForm(
        data=_crossref_post_data(crossref_plus_api_token="new-token"), instance=_existing_prefs()
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert calls == ["new-token"]
    assert saved.crossref_plus_api_token == "new-token"


@pytest.mark.django_db
def test__crossref_token__rejected_token_is_never_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "coda.apps.preferences.forms.crossref_access.verify_plus_token", _verify_rejected
    )
    form = CrossrefAccessForm(
        data=_crossref_post_data(crossref_plus_api_token="bad-token"), instance=_existing_prefs()
    )
    assert not form.is_valid()
    assert "Crossref does not accept this key" in form.errors["crossref_plus_api_token"][0]
    assert not GlobalPreferences.objects.exclude(crossref_plus_api_token="").exists()


@pytest.mark.django_db
def test__crossref_token__unreachable_crossref__token_not_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "coda.apps.preferences.forms.crossref_access.verify_plus_token", _verify_unreachable
    )
    form = CrossrefAccessForm(
        data=_crossref_post_data(crossref_plus_api_token="some-token"), instance=_existing_prefs()
    )
    assert not form.is_valid()
    assert "Could not reach Crossref" in form.errors["crossref_plus_api_token"][0]
    assert not GlobalPreferences.objects.exclude(crossref_plus_api_token="").exists()


@pytest.mark.django_db
def test__crossref_token__no_plus_pool_confirmation__token_not_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "coda.apps.preferences.forms.crossref_access.verify_plus_token",
        lambda token, timeout=5: (
            200,
            {"x-api-pool": "public", "x-rate-limit-limit": "5", "x-rate-limit-interval": "1s"},
        ),
    )
    form = CrossrefAccessForm(
        data=_crossref_post_data(crossref_plus_api_token="odd-token"), instance=_existing_prefs()
    )
    assert not form.is_valid()
    assert "could not confirm the faster access" in form.errors["crossref_plus_api_token"][0]
    assert not GlobalPreferences.objects.exclude(crossref_plus_api_token="").exists()


@pytest.mark.django_db
def test__crossref_token__posting_mask_keeps_existing_when_verification_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Posting the mask keeps the stored value even when Crossref is down."""
    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "already-verified-token"
    prefs.save()

    monkeypatch.setattr(
        "coda.apps.preferences.forms.crossref_access.verify_plus_token",
        _verify_unreachable,
    )
    update = CrossrefAccessForm(
        instance=prefs,
        data=_crossref_post_data(crossref_plus_api_token=TOKEN_MASK),
    )
    assert update.is_valid(), update.errors
    update.save()

    saved = GlobalPreferences.objects.get()
    assert saved.crossref_plus_api_token == "already-verified-token"


@pytest.mark.django_db
def test__crossref_token__field_absent_from_post__leaves_stored_token_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale/programmatic POST without the token field must not wipe the key."""
    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "untouched-key"
    prefs.save()

    def fail(*args: object, **kwargs: object) -> tuple[int | None, dict[str, str]]:
        raise AssertionError("absent field must not verify anything")

    monkeypatch.setattr("coda.apps.preferences.forms.crossref_access.verify_plus_token", fail)

    data = _crossref_post_data()
    del data["crossref_contact_email"]
    # No crossref_plus_api_token key at all.
    form = CrossrefAccessForm(data=data, instance=prefs)
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.crossref_plus_api_token == "untouched-key"


@pytest.mark.django_db
def test__crossref_token__whitespace_only_input__treated_as_removal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace-only input is not a key and must not crash verification."""
    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "stored-token"
    prefs.save()

    def fail(*args: object, **kwargs: object) -> tuple[int | None, dict[str, str]]:
        raise AssertionError("whitespace input must not reach verification")

    monkeypatch.setattr("coda.apps.preferences.forms.crossref_access.verify_plus_token", fail)

    form = CrossrefAccessForm(
        data=_crossref_post_data(crossref_plus_api_token="   "), instance=prefs
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.crossref_plus_api_token == ""


@pytest.mark.django_db
def test__crossref_token__typed_key_rerender_resubmit__reverifies_new_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An error rerender echoes a typed key verbatim, not as the mask.

    Otherwise a user who fixes the email error and resubmits would send the
    mask, which clean() reads as "keep the stored token" — silently
    discarding the new key.
    """
    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "stored-token"
    prefs.save()

    # First submit: typed key, missing email -> invalid.
    form = CrossrefAccessForm(data={"crossref_plus_api_token": "typed-new-key"}, instance=prefs)
    assert not form.is_valid()
    # The bound field echoes the typed value verbatim (not the mask).
    rendered = str(form["crossref_plus_api_token"])
    assert "typed-new-key" in rendered
    assert TOKEN_MASK not in rendered

    # Resubmit the echoed value with the email added -> new key is verified.
    monkeypatch.setattr("coda.apps.preferences.forms.crossref_access.verify_plus_token", _verify_ok)
    resubmitted = CrossrefAccessForm(
        data={
            "crossref_plus_api_token": "typed-new-key",
            "crossref_contact_email": "c@e.org",
        },
        instance=prefs,
    )
    assert resubmitted.is_valid(), resubmitted.errors
    saved = resubmitted.save()
    assert saved.crossref_plus_api_token == "typed-new-key"


@pytest.mark.django_db
def test__crossref_token_field__renders_mask_for_stored_token_only() -> None:
    unconfigured = CrossrefAccessForm(instance=_existing_prefs())
    # No stored key: the field renders empty, no mask, no value.
    unconfigured_rendered = str(unconfigured["crossref_plus_api_token"])
    assert "value=" not in unconfigured_rendered

    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "stored-token"
    prefs.save()

    configured = CrossrefAccessForm(instance=prefs)
    # The rendered widget carries the mask, never the secret, and the input
    # is password-masked on screen.
    rendered = str(configured["crossref_plus_api_token"])
    assert "stored-token" not in rendered
    assert f'value="{TOKEN_MASK}"' in rendered
    assert 'type="password"' in rendered


# --- Crossref token status (on-demand verification) --------------------------


@pytest.mark.django_db
def test__check_stored_token__no_token__unverified() -> None:
    from coda.contexts.fundingrequest.services.doi_import.crossref_access import check_stored_token

    status, message, has_token = check_stored_token()
    assert status == "unverified"
    assert "No key is saved" in message
    assert has_token is False


@pytest.mark.django_db
def test__check_stored_token__valid_token__verified_with_pool_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coda.contexts.fundingrequest.services.doi_import.crossref_access import check_stored_token

    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "stored-token"
    prefs.save()
    monkeypatch.setattr(
        "coda.contexts.fundingrequest.services.doi_import.crossref_access.verify_plus_token",
        lambda token, timeout=5: (
            200,
            {
                "x-api-pool": "plus-array",
                "x-rate-limit-limit": "150",
                "x-rate-limit-interval": "1s",
            },
        ),
    )

    status, message, has_token = check_stored_token()
    assert status == "verified"
    assert "requests per" in message
    assert has_token is True


@pytest.mark.django_db
def test__check_stored_token__expired_token__rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coda.contexts.fundingrequest.services.doi_import.crossref_access import check_stored_token

    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "expired-token"
    prefs.save()
    monkeypatch.setattr(
        "coda.contexts.fundingrequest.services.doi_import.crossref_access.verify_plus_token",
        lambda token, timeout=5: (401, {}),
    )

    status, message, has_token = check_stored_token()
    assert status == "rejected"
    assert "error 401" in message
    assert has_token is True


@pytest.mark.django_db
def test__check_stored_token__crossref_unreachable__unverified_not_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coda.contexts.fundingrequest.services.doi_import.crossref_access import check_stored_token

    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "some-token"
    prefs.save()
    monkeypatch.setattr(
        "coda.contexts.fundingrequest.services.doi_import.crossref_access.verify_plus_token",
        lambda token, timeout=5: (None, {}),
    )

    status, message, has_token = check_stored_token()
    assert status == "unverified"
    assert "validity is unknown" in message
    assert has_token is True


@pytest.mark.django_db
def test__check_stored_token__transient_error__leaves_flag_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 429/5xx during a status check must not mark a working key invalid."""
    from coda.contexts.fundingrequest.services.doi_import.crossref_access import check_stored_token

    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "good-key"
    prefs.crossref_plus_api_token_valid = True
    prefs.save()
    monkeypatch.setattr(
        "coda.contexts.fundingrequest.services.doi_import.crossref_access.verify_plus_token",
        lambda token, timeout=5: (429, {}),
    )

    status, message, has_token = check_stored_token()
    assert status == "unverified"
    assert "error 429" in message
    assert has_token is True
    assert GlobalPreferences.objects.get().crossref_plus_api_token_valid is True


@pytest.mark.django_db
def test__check_stored_token__verified__resets_invalid_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verified re-check re-enables a key that was marked invalid."""
    from coda.contexts.fundingrequest.services.doi_import.crossref_access import check_stored_token

    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "was-rejected"
    prefs.crossref_plus_api_token_valid = False
    prefs.save()
    monkeypatch.setattr(
        "coda.contexts.fundingrequest.services.doi_import.crossref_access.verify_plus_token",
        lambda token, timeout=5: (200, {"x-api-pool": "plus-array"}),
    )

    status, _, _ = check_stored_token()
    assert status == "verified"
    assert GlobalPreferences.objects.get().crossref_plus_api_token_valid is True


@pytest.mark.django_db
def test__check_stored_token__rejected__sets_invalid_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coda.contexts.fundingrequest.services.doi_import.crossref_access import check_stored_token

    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "now-expired"
    prefs.save()
    monkeypatch.setattr(
        "coda.contexts.fundingrequest.services.doi_import.crossref_access.verify_plus_token",
        lambda token, timeout=5: (401, {}),
    )

    status, _, _ = check_stored_token()
    assert status == "rejected"
    assert GlobalPreferences.objects.get().crossref_plus_api_token_valid is False


@pytest.mark.django_db
def test__check_stored_token__unreachable__leaves_flag_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient network failure must not clear a genuine rejection."""
    from coda.contexts.fundingrequest.services.doi_import.crossref_access import check_stored_token

    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "marked-invalid"
    prefs.crossref_plus_api_token_valid = False
    prefs.save()
    monkeypatch.setattr(
        "coda.contexts.fundingrequest.services.doi_import.crossref_access.verify_plus_token",
        lambda token, timeout=5: (None, {}),
    )

    check_stored_token()
    assert GlobalPreferences.objects.get().crossref_plus_api_token_valid is False


# --- Views -------------------------------------------------------------------


@pytest.mark.django_db
def test__crossref_token_status_view__renders_status_fragment(
    client: "Client",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coda.apps.users.models import User

    user, _ = User.objects.get_or_create(
        username="status-viewer", defaults={"is_staff": True, "is_superuser": True}
    )
    client.force_login(user)
    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "stored-token"
    prefs.save()
    monkeypatch.setattr(
        "coda.contexts.fundingrequest.services.doi_import.crossref_access.check_stored_token",
        lambda: (
            "rejected",
            "Crossref no longer accepts the saved key (error 401). It may have expired or been revoked.",
            True,
        ),
    )

    response = client.post(reverse("preferences:crossref_token_status"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "✗" in content
    assert "error 401" in content
    assert 'hx-post="' in content  # re-check button wired


@pytest.mark.django_db
def test__crossref_token_status_view__no_token__no_recheck_button(
    client: "Client",
) -> None:
    from coda.apps.users.models import User

    user, _ = User.objects.get_or_create(
        username="status-no-token", defaults={"is_staff": True, "is_superuser": True}
    )
    client.force_login(user)

    response = client.post(reverse("preferences:crossref_token_status"))
    assert response.status_code == 200
    content = response.content.decode()
    assert "No key is saved" in content
    assert 'hx-post="' not in content  # nothing to re-check


@pytest.mark.django_db
def test__preferences_page__renders_two_sections_with_separate_forms(
    client: "Client",
) -> None:
    from coda.apps.users.models import User

    user, _ = User.objects.get_or_create(
        username="prefs-viewer", defaults={"is_staff": True, "is_superuser": True}
    )
    client.force_login(user)

    response = client.get(reverse("preferences:global_preferences"))
    content = response.content.decode()
    assert "Crossref Metadata Access" in content
    assert 'name="crossref_contact_email"' in content
    assert 'hx-post="' in content and "crossref" in content  # card routes via htmx
    assert content.count("<form") >= 2  # general + crossref sections


@pytest.mark.django_db
def test__preferences_page__token_status_footer_hidden_without_token(
    client: "Client",
) -> None:
    from coda.apps.users.models import User

    user, _ = User.objects.get_or_create(
        username="prefs-no-token", defaults={"is_staff": True, "is_superuser": True}
    )
    client.force_login(user)

    response = client.get(reverse("preferences:global_preferences"))
    content = response.content.decode()
    assert "crossref-token-status" not in content  # footer hidden without a key
    assert "Check key status" not in content


@pytest.mark.django_db
def test__preferences_page__token_status_shows_check_button_with_token(
    client: "Client",
) -> None:
    from coda.apps.users.models import User

    user, _ = User.objects.get_or_create(
        username="prefs-with-token", defaults={"is_staff": True, "is_superuser": True}
    )
    client.force_login(user)
    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "stored-token"
    prefs.save()

    response = client.get(reverse("preferences:global_preferences"))
    content = response.content.decode()
    assert "key status: not checked yet" in content
    assert "Check key status" in content


@pytest.mark.django_db
def test__crossref_section_post__failed_save__swaps_card_without_stored_state(
    client: "Client",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid POST returns only the card fragment; footer reflects storage.

    htmx swaps the card in place, so the browser URL stays on the
    preferences page and the rest of the page is untouched. The footer must
    not behave as if the typed (unsaved) key were stored.
    """
    from coda.apps.users.models import User

    user, _ = User.objects.get_or_create(
        username="section-failed", defaults={"is_staff": True, "is_superuser": True}
    )
    client.force_login(user)
    # Pin the precondition: the singleton row starts without a stored key,
    # regardless of what sibling tests saved (shared row, xdist + reuse-db).
    GlobalPreferences.objects.update(crossref_plus_api_token="")
    monkeypatch.setattr(
        "coda.apps.preferences.forms.crossref_access.verify_plus_token",
        _verify_rejected,
    )

    data = _crossref_post_data(crossref_plus_api_token="bad-token")
    response = client.post(
        reverse("preferences:crossref_settings"), data, headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="crossref-card"' in content
    assert "General Preferences" not in content  # fragment, not the full page
    assert "<html" not in content
    assert "Crossref does not accept this key" in content
    assert "crossref-token-status" not in content  # footer hidden: no key stored
    assert "Check key status" not in content


@pytest.mark.django_db
def test__crossref_section_post__no_js_fallback__renders_full_page(
    client: "Client",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the htmx header, an invalid POST renders the complete page."""
    from coda.apps.users.models import User

    user, _ = User.objects.get_or_create(
        username="section-nojs", defaults={"is_staff": True, "is_superuser": True}
    )
    client.force_login(user)
    monkeypatch.setattr(
        "coda.apps.preferences.forms.crossref_access.verify_plus_token",
        _verify_rejected,
    )

    data = _crossref_post_data(crossref_plus_api_token="bad-token")
    response = client.post(reverse("preferences:crossref_settings"), data)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Crossref does not accept this key" in content
    assert "General Preferences" in content  # full page, both cards
    assert 'name="home_currency"' in content


@pytest.mark.django_db
def test__crossref_section_post__success__redirects_via_htmx(
    client: "Client",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coda.apps.users.models import User

    user, _ = User.objects.get_or_create(
        username="section-poster", defaults={"is_staff": True, "is_superuser": True}
    )
    client.force_login(user)
    monkeypatch.setattr(
        "coda.apps.preferences.forms.crossref_access.verify_plus_token",
        _verify_ok,
    )

    data = _crossref_post_data(crossref_plus_api_token="posted-token")
    response = client.post(
        reverse("preferences:crossref_settings"), data, headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    assert response["HX-Redirect"] == reverse("preferences:global_preferences")
    saved = GlobalPreferences.objects.get()
    assert saved.crossref_plus_api_token == "posted-token"

    # The confirmation flash renders on the page htmx navigates to.
    page = client.get(reverse("preferences:global_preferences"))
    assert "Crossref settings updated" in page.content.decode()


@pytest.mark.django_db
def test__crossref_section_post__success__no_js__redirects_with_302(
    client: "Client",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without htmx, a successful save is a plain redirect, not a blank 200."""
    from coda.apps.users.models import User

    user, _ = User.objects.get_or_create(
        username="nojs-saver", defaults={"is_staff": True, "is_superuser": True}
    )
    client.force_login(user)
    monkeypatch.setattr("coda.apps.preferences.forms.crossref_access.verify_plus_token", _verify_ok)

    data = _crossref_post_data(crossref_plus_api_token="posted-token")
    response = client.post(reverse("preferences:crossref_settings"), data)

    assert response.status_code == 302
    assert response["Location"] == reverse("preferences:global_preferences")


@pytest.mark.django_db
def test__crossref_token__save_with_typed_key__resets_invalid_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Saving a newly typed (verified) key re-enables its use."""
    from coda.apps.users.models import User

    User.objects.get_or_create(
        username="typed-key-saver", defaults={"is_staff": True, "is_superuser": True}
    )
    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "old-invalid"
    prefs.crossref_plus_api_token_valid = False
    prefs.save()
    monkeypatch.setattr("coda.apps.preferences.forms.crossref_access.verify_plus_token", _verify_ok)

    form = CrossrefAccessForm(
        data=_crossref_post_data(crossref_plus_api_token="fresh-key"),
        instance=prefs,
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.crossref_plus_api_token == "fresh-key"
    assert saved.crossref_plus_api_token_valid is True


@pytest.mark.django_db
def test__crossref_token__save_keeping_stored_key__keeps_invalid_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mask ("keep") path must not re-enable a marked key."""
    from coda.apps.users.models import User

    User.objects.get_or_create(
        username="keep-key-saver", defaults={"is_staff": True, "is_superuser": True}
    )
    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "still-invalid"
    prefs.crossref_plus_api_token_valid = False
    prefs.save()
    monkeypatch.setattr("coda.apps.preferences.forms.crossref_access.verify_plus_token", _verify_ok)

    form = CrossrefAccessForm(
        data=_crossref_post_data(crossref_plus_api_token=TOKEN_MASK), instance=prefs
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.crossref_plus_api_token == "still-invalid"
    assert saved.crossref_plus_api_token_valid is False


@pytest.mark.django_db
def test__preferences_page__renders_mask_and_never_the_secret(client: "Client") -> None:
    """The served page shows the mask; the stored secret never reaches HTML."""
    from coda.apps.users.models import User

    user, _ = User.objects.get_or_create(
        username="mask-renderer", defaults={"is_staff": True, "is_superuser": True}
    )
    client.force_login(user)
    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "super-secret-value"
    prefs.save()

    content = client.get(reverse("preferences:global_preferences")).content.decode()
    assert f'value="{TOKEN_MASK}"' in content
    assert 'type="password"' in content
    assert "super-secret-value" not in content


@pytest.mark.django_db
def test__preferences_page__rendered_mask_round_trips_as_keep(
    client: "Client", monkeypatch: pytest.MonkeyPatch
) -> None:
    """POSTing back exactly what the page rendered keeps the stored key.

    Both sides of the mask protocol are usually pinned to the same Python
    constant; this test extracts the value the template actually rendered
    and submits that string, so a render/parse mismatch breaks here.
    """
    import re

    from coda.apps.users.models import User

    user, _ = User.objects.get_or_create(
        username="mask-roundtrip", defaults={"is_staff": True, "is_superuser": True}
    )
    client.force_login(user)
    prefs = _existing_prefs()
    prefs.crossref_plus_api_token = "roundtrip-stored-key"
    prefs.save()

    page = client.get(reverse("preferences:global_preferences")).content.decode()
    match = re.search(r'name="crossref_plus_api_token"[^>]*value="([^"]*)"', page)
    assert match is not None, "token field with a value not found on the page"
    rendered_value = match.group(1)

    def fail(*args: object, **kwargs: object) -> tuple[int | None, dict[str, str]]:
        raise AssertionError("keeping the rendered mask must not verify against Crossref")

    monkeypatch.setattr("coda.apps.preferences.forms.crossref_access.verify_plus_token", fail)

    response = client.post(
        reverse("preferences:crossref_settings"),
        {"crossref_contact_email": "c@e.org", "crossref_plus_api_token": rendered_value},
    )
    assert response.status_code == 302
    saved = GlobalPreferences.objects.get()
    assert saved.crossref_plus_api_token == "roundtrip-stored-key"
