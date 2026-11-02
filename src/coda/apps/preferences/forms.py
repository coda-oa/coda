import typing
from typing import cast

from django import forms

from coda.apps import fields
from coda.apps.preferences.models import GlobalPreferences
from coda.contexts.fundingrequest.services.doi_import import crossref_access

TOKEN_MASK = "********"


class GlobalPreferencesForm(forms.ModelForm[GlobalPreferences]):
    """General preferences: home currency and default vocabularies."""

    home_currency = fields.currency_field(label="Home currency")

    class Meta:
        model = GlobalPreferences
        fields: typing.ClassVar[list[str]] = [
            "home_currency",
            "home_institution",
            "subject_classification_vocabulary",
            "article_publication_type_vocabulary",
            "monograph_publication_type_vocabulary",
        ]


class CrossrefAccessForm(forms.ModelForm[GlobalPreferences]):
    """Crossref API access: contact email and Metadata Plus token.

    The stored token is displayed as a fixed mask (``TOKEN_MASK``); the real
    secret never appears in the rendered HTML. Four states for the token
    field in POST data:

    - absent from the POST (stale/programmatic submit): stored token is
      left untouched.
    - ``TOKEN_MASK``: keep the stored token (it was verified when saved).
    - present but empty: remove the stored token.
    - anything else: a new token, verified against Crossref before saving.

    Re-check the stored token via the status endpoint, which also catches
    tokens expiring after they were saved.
    """

    class MaskedPasswordInput(forms.PasswordInput):
        """Renders values as-is; masking of the *stored* value happens in
        :meth:`MaskedTokenField.prepare_value`, so user-typed values echo
        back verbatim on error rerenders instead of being rewritten to the
        mask (which would turn a resubmit into "keep the stored token").
        """

        def __init__(self, attrs: dict[str, typing.Any] | None = None) -> None:
            super().__init__(attrs=attrs, render_value=True)

    class MaskedTokenField(forms.CharField):
        """Displays the stored token as ``TOKEN_MASK``, never the secret.

        Only the stored value is masked. A typed-but-rejected value echoes
        back verbatim on the error rerender, so resubmitting it re-verifies
        the same key instead of silently keeping the stored one.
        """

        _stored_token: str = ""

        def prepare_value(self, value: typing.Any) -> typing.Any:
            if value and value != TOKEN_MASK and value == self._stored_token:
                return TOKEN_MASK
            return value

    crossref_plus_api_token = MaskedTokenField(
        label="Crossref Metadata Plus API token",
        required=False,
        widget=MaskedPasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=(
            "Optional key for faster access to Crossref (150 requests per second instead of 5). "
            f"Leave as {TOKEN_MASK} to keep the saved key; empty the field to remove it. "
            "Enter a new key to replace the saved one. "
            "Your contact email above is required when a key is used. "
            "The key is checked with Crossref before it is saved. "
            "An invalid or expired key is not accepted."
        ),
    )

    class Meta:
        model = GlobalPreferences
        fields: typing.ClassVar[list[str]] = ["crossref_contact_email", "crossref_plus_api_token"]

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        super().__init__(*args, **kwargs)
        stored = self.instance.crossref_plus_api_token if self.instance and self.instance.pk else ""
        token_field = cast(
            "CrossrefAccessForm.MaskedTokenField", self.fields["crossref_plus_api_token"]
        )
        token_field._stored_token = stored
        if stored:
            # Render the stored token as the mask. POSTing the mask back
            # means "keep it" (see clean()); emptying the field removes it.
            self.initial["crossref_plus_api_token"] = TOKEN_MASK

    def clean(self) -> dict[str, object]:
        cleaned = cast(dict[str, object], super().clean())
        # Whitespace-only input is not a key; treat it as an attempt to
        # remove (a real key cannot consist of whitespace, and
        # CrossrefPoliteness would raise ValueError on it otherwise).
        raw_token = str(cleaned.get("crossref_plus_api_token") or "")
        token = raw_token.strip()
        cleaned["crossref_plus_api_token"] = token
        email = str(cleaned.get("crossref_contact_email") or "")

        if token == TOKEN_MASK:
            # The mask round-trips the stored token: keep it, unverified (it
            # was verified when saved; re-check via the status endpoint).
            stored = (
                self.instance.crossref_plus_api_token if self.instance and self.instance.pk else ""
            )
            cleaned["crossref_plus_api_token"] = stored
            return cleaned

        if not token:
            # Empty field: remove the stored token, no verification needed.
            cleaned["crossref_plus_api_token"] = ""
            return cleaned

        # A newly entered token: verify before persisting.
        if token and not email:
            self.add_error(
                "crossref_contact_email",
                "Please enter your contact email. Crossref requires it when a key is used. "
                "They may need to reach you if something goes wrong.",
            )
            return cleaned

        # Never persist an unverified token: Crossref must have accepted this
        # exact value before it is stored.
        status, headers = crossref_access.verify_plus_token(token)
        if status is None:
            self.add_error(
                "crossref_plus_api_token",
                "Could not reach Crossref to check the key right now. "
                "Nothing was saved. Please try again later.",
            )
        elif status != 200:
            self.add_error(
                "crossref_plus_api_token",
                f"Crossref does not accept this key (error {status}). "
                "Nothing was saved. Please check the key and try again.",
            )
        elif not headers.get("x-api-pool", "").startswith("plus"):
            self.add_error(
                "crossref_plus_api_token",
                "Crossref accepted the key, but could not confirm the faster access it should provide. "
                "Nothing was saved.",
            )

        return cleaned

    def save(self, commit: bool = True) -> GlobalPreferences:
        """Persist preferences, honoring the mask round-trip semantics.

        The token field's ``clean()`` has already resolved the four cases:
        absent → stored token untouched, mask → stored token (keep,
        unverified), empty → "" (remove), other → a verified new token.

        The remove/keep/new decisions below read the *raw* POST data rather
        than ``cleaned_data``: on a validation error (e.g. a rejected new
        key) ``cleaned_data["crossref_plus_api_token"]`` is deleted, and
        deriving the decision from it would wipe the stored key.
        """
        if not self.is_valid():
            raise ValueError("Cannot save an invalid CrossrefAccessForm")
        instance = super().save(commit=False)
        submitted = "crossref_plus_api_token" in self.data
        typed = self.data.get("crossref_plus_api_token") or ""
        entered = str(self.cleaned_data.get("crossref_plus_api_token") or "")
        if submitted and not entered:
            instance.crossref_plus_api_token = ""
            # No key, no verdict.
            instance.crossref_plus_api_token_valid = None
        elif submitted and typed != TOKEN_MASK:
            # A newly typed key has just been verified by clean(); assume
            # valid and re-enable its use. The mask ("keep") path must NOT
            # reset validity: a stored key marked invalid stays invalid
            # until re-checked via the status button.
            instance.crossref_plus_api_token_valid = True
        # Field absent from the POST: leave the stored token untouched.

        if commit:
            instance.save()
        return instance
