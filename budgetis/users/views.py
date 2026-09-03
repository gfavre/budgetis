from collections import defaultdict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Max
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import UpdateView

from budgetis.accounting.models import Account
from budgetis.users.forms import UserProfileForm
from budgetis.users.models import User


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "id"
    slug_url_kwarg = "id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object == self.request.user:
            context["profile_form"] = UserProfileForm(instance=self.object)
            context["responsibility_sections"] = self._current_year_responsibility_sections()
        return context

    def _current_year_responsibility_sections(self) -> list[dict]:
        """
        The user's responsible groups and their individual accounts (not just
        the group), limited to the most recent year they have a
        responsibility in - past years' assignments aren't relevant day-to-day.
        """
        current_year = self.object.account_groups.aggregate(Max("year"))["year__max"]
        if current_year is None:
            return []

        responsibilities = list(
            self.object.account_groups.filter(year=current_year).select_related("group").order_by("group__code")
        )
        accounts = (
            Account.objects.filter(group_id__in=[r.group_id for r in responsibilities], year=current_year)
            .order_by("group_id", "function", "nature", "sub_account")
            .distinct("group_id", "function", "nature", "sub_account")
        )
        accounts_by_group_id = defaultdict(list)
        for account in accounts:
            accounts_by_group_id[account.group_id].append(account)

        return [{"group": r.group, "accounts": accounts_by_group_id[r.group_id]} for r in responsibilities]


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    success_message = _("Information successfully updated")

    def get_success_url(self) -> str:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user.get_absolute_url()

    def get_object(self, queryset: QuerySet | None = None) -> User:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self) -> str:
        return reverse("users:detail", kwargs={"pk": self.request.user.pk})


user_redirect_view = UserRedirectView.as_view()
