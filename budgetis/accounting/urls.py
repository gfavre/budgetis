from django.urls import path

from .views.explore import AccountExplorerView
from .views.explore import AccountPartialView
from .views.history import account_history_modal


app_name = "accounting"

urlpatterns = [
    path("explorer/", AccountExplorerView.as_view(), name="account-explorer"),
    path("explorer/partial/", AccountPartialView.as_view(), name="account-partial"),
    path("history/<int:account_id>/", account_history_modal, name="account-history"),
]
