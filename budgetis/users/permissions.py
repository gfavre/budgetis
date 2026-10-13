from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.mixins import UserPassesTestMixin

from budgetis.users.models import BOURSE_GROUP_NAME


def can_manage_platform(user) -> bool:
    return (
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.is_staff or user.groups.filter(name=BOURSE_GROUP_NAME).exists())
    )


class PlatformSettingsMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return can_manage_platform(self.request.user)
