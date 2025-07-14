from django.shortcuts import render

def index(request):
    return render(request, "infopage/info_page.html")