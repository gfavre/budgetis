from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView
from django.views.generic import DeleteView
from django.views.generic import ListView
from django.views.generic import UpdateView

from ..forms import AccountCommentForm
from ..models import Account
from ..models import AccountComment


class AccountCommentsView(LoginRequiredMixin, ListView):
    """
    Display the list of comments for a given account and kind (charges, revenues, etc.).
    Rendered as a partial for htmx inside the modal.
    """

    model = AccountComment
    template_name = "accounting/account_comments_list.html"
    context_object_name = "comments"

    def get_queryset(self):
        account_id = self.kwargs["account_id"]
        self.account = get_object_or_404(Account, pk=account_id)
        return self.account.comments.all().order_by("created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["account"] = self.account
        ctx["kind"] = self.kwargs["kind"]
        ctx["group_accounts"] = (
            self.account.group.accounts.filter(year=self.account.year, is_budget=self.account.is_budget)
            .prefetch_related("comments")
            .all()
        )
        return ctx


class AccountCommentCreateView(LoginRequiredMixin, CreateView):
    """
    Create a new comment for a given account.
    """

    model = AccountComment
    form_class = AccountCommentForm
    template_name = "accounting/partials/account_comment_form.html"

    def get_success_url(self):
        return reverse_lazy(
            "accounting:account-comments",
            kwargs={
                "account_id": self.kwargs["account_id"],
                "kind": self.kwargs["kind"],
            },
        )

    def form_valid(self, form):
        form.instance.account = get_object_or_404(Account, pk=self.kwargs["account_id"])
        form.instance.author = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["account"] = get_object_or_404(Account, pk=self.kwargs["account_id"])
        ctx["kind"] = self.kwargs["kind"]
        return ctx


class AccountCommentEditView(LoginRequiredMixin, UpdateView):
    """
    Edit an existing comment.
    """

    model = AccountComment
    form_class = AccountCommentForm
    template_name = "accounting/partials/account_comment_form.html"

    def get_success_url(self):
        return reverse_lazy(
            "accounting:account-comments",
            kwargs={
                "account_id": self.object.account.id,
                "kind": self.kwargs.get("kind", "charges"),
            },
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["account"] = self.object.account
        ctx["kind"] = self.kwargs.get("kind", "charges")
        return ctx


class AccountCommentDeleteView(LoginRequiredMixin, DeleteView):
    """
    Delete an existing comment.
    HTMX will reload the comments list on success.
    """

    model = AccountComment
    template_name = "accounting/partials/account_comment_confirm_delete.html"

    def get_success_url(self):
        return reverse_lazy(
            "accounting:account-comments",
            kwargs={
                "account_id": self.object.account.id,
                "kind": self.kwargs.get("kind", "charges"),
            },
        )
