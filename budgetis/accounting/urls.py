from django.urls import path

from .views.explore import AccountExplorerView
from .views.explore import AccountPartialView


app_name = "accounting"

urlpatterns = [
    path("explorer/", AccountExplorerView.as_view(), name="account-explorer"),
    path("explorer/partial/", AccountPartialView.as_view(), name="account-partial"),
]
