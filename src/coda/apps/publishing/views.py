from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def publishing_home(request: HttpRequest) -> HttpResponse:
    return render(request, "publishing/home.html")
