"""Session-checking decorators for funding request views.

Provides a ``require_session`` factory that creates decorators for checking
that a named session key exists before the view runs.
"""

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar, cast

from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.urls import reverse
from django_htmx.http import HttpResponseClientRedirect

from coda.apps.htmx_components.request import HtmxHttpRequest

P = ParamSpec("P")
R = TypeVar("R", bound=HttpResponse)

SESSION_NOT_FOUND = "Preview session not found or expired"


def require_session(
    key: str = "session_key",
    message: str = SESSION_NOT_FOUND,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Return a decorator that guards a session-backed view.

    On a missing session key, htmx requests get ``HX-Redirect`` to the DOI
    import input page (htmx 2 does not swap 4xx responses, so a 404 would
    leave the htmx action dead); plain requests keep the 404 — the preview
    URL is transient and a redirect would mask a dead bookmark as a live one.

    Works on both function-based views (no ``self``) and methods of
    class-based views (with ``self``).

    Examples::

        @require_session()
        def preview_detail(request, session_key): ...

        @require_session("result_key", "Result session not found or expired")
        def result_view(request, result_key): ...

    The decorated view/method still performs its own session lookup for the
    actual data — the decorator only handles the guard clause and the
    centralised error message.
    """

    def decorator(view_func: Callable[P, R]) -> Callable[P, R]:
        @wraps(view_func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # args[0] is self (method) or request (function)
            if args and isinstance(args[0], HttpRequest):
                request = cast(HttpRequest, args[0])
            else:
                request = cast(HttpRequest, args[1])

            session_data = request.session.get(cast(str, kwargs[key]))
            if not session_data:
                if cast(HtmxHttpRequest, request).htmx:
                    return cast(
                        R,
                        HttpResponseClientRedirect(reverse("fundingrequests:doi_import_input")),
                    )
                return HttpResponseNotFound(message)  # type: ignore[return-value]

            return view_func(*args, **kwargs)

        return wrapper

    return decorator
