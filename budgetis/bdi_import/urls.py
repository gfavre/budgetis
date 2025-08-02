# urls.py
from django.urls import path

from .views import AccountImportView
from .views import AccountMappingView


app_name = "bdi_import"

urlpatterns = [
    path("import/", AccountImportView.as_view(), name="account-import"),
    path("mapping/<int:log_id>/", AccountMappingView.as_view(), name="account-mapping"),
]
