from django.urls import path
from .views import invoice_list, invoice_detail

app_name = "invoices"

urlpatterns = [
    path("", invoice_list, name="list"),
    path("<int:pk>/", invoice_detail, name="detail"),
]
