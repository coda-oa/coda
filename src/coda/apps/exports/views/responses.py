from django.http import HttpResponse
from django.utils.http import content_disposition_header


def stored_artifact_response(
    content: str,
    *,
    content_type: str,
    filename: str,
    encoding: str = "utf-8",
) -> HttpResponse:
    """Serve a stored export artifact as a downloadable response."""
    response = HttpResponse(content.encode(encoding), content_type=content_type)
    response["Content-Disposition"] = content_disposition_header(True, filename)
    return response
