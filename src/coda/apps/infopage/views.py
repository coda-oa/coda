from django.shortcuts import render

from django.views.decorators.http import require_GET

@require_GET
def index(request):
    return render(request, "infopage/info_page.html")