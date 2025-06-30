# urls.py
from django.urls import path

from .views import AccountImportView


app_name = "bdi_import"

urlpatterns = [
    path("import/", AccountImportView.as_view(), name="account-import"),
]
