# urls.py
from django.urls import path

from .views import AccountImportView
from .views import AccountMappingView
from .views import ExcelImportView


app_name = "bdi_import"

urlpatterns = [
    path("import/", AccountImportView.as_view(), name="account-import"),
    path("import-excel/", ExcelImportView.as_view(), name="excel-import"),
    path("mapping/<int:log_id>/", AccountMappingView.as_view(), name="account-mapping"),
]
