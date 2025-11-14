from django.urls import path

# from .views.budget_compare import BudgetComparisonView
from .views.comments import AccountCommentCreateView
from .views.comments import AccountCommentDeleteView
from .views.comments import AccountCommentEditView
from .views.comments import AccountCommentsView
from .views.explore import AccountExplorerView
from .views.explore import AccountPartialView
from .views.explore import BudgetByNaturePartialView
from .views.explore import BudgetByNatureView
from .views.explore import BudgetExplorerView
from .views.explore import BudgetPartialView
from .views.history import account_history_modal


app_name = "accounting"

urlpatterns = [
    path("accounts/", AccountExplorerView.as_view(), name="account-explorer"),
    path("accounts/partial/", AccountPartialView.as_view(), name="account-partial"),
    # Budgets
    path("budgets/", BudgetExplorerView.as_view(), name="budget-explorer"),
    path("budgets/partial/", BudgetPartialView.as_view(), name="budget-partial"),
    path("budgets-nature/", BudgetByNatureView.as_view(), name="budget-nature-explorer"),
    path("budgets-nature/partial/", BudgetByNaturePartialView.as_view(), name="budget-nature-partial"),
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
    ##path("budget/compare/", BudgetComparisonView.as_view(), name="budget-compare"),
]
