from django.urls import path

from .views.comments import AccountCommentCreateView
from .views.comments import AccountCommentDeleteView
from .views.comments import AccountCommentEditView
from .views.comments import AccountCommentsView
from .views.explore import AccountExplorerView
from .views.explore import AccountPartialView
from .views.history import account_history_modal


app_name = "accounting"

urlpatterns = [
    path("explorer/", AccountExplorerView.as_view(), name="account-explorer"),
    path("explorer/partial/", AccountPartialView.as_view(), name="account-partial"),
    path("history/<int:account_id>/", account_history_modal, name="account-history"),
    path(
        "comments/<int:pk>/edit/",
        AccountCommentEditView.as_view(),
        name="account-comment-edit",
    ),
    path(
        "comments/<int:pk>/delete/",
        AccountCommentDeleteView.as_view(),
        name="account-comment-delete",
    ),
    path(
        "comments/<int:account_id>/<str:kind>/new/",
        AccountCommentCreateView.as_view(),
        name="account-comment-create",
    ),
    path(
        "comments/<int:account_id>/<str:kind>/",
        AccountCommentsView.as_view(),
        name="account-comments",
    ),
]
