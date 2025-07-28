from django.urls import path

from .views import AccountExplorerView


app_name = "accounting"

urlpatterns = [
    path("explorer/", AccountExplorerView.as_view(), name="account-explorer"),
]
