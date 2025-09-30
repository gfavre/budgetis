from __future__ import annotations

import typing

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

from budgetis.users.models import User


if typing.TYPE_CHECKING:
    from allauth.socialaccount.models import SocialLogin
    from django.http import HttpRequest


from budgetis.users.models import AuthorizedEmail


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return getattr(settings, "ACCOUNT_ALLOW_REGISTRATION", True)


class MunicipalSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        # Refuser toute création automatique
        email = sociallogin.user.email
        return AuthorizedEmail.objects.filter(email__iexact=email).exists()

    def populate_user(
        self,
        request: HttpRequest,
        sociallogin: SocialLogin,
        data: dict[str, typing.Any],
    ) -> User:
        """
        Populates user information from social provider info.

        See: https://docs.allauth.org/en/latest/socialaccount/advanced.html#creating-and-populating-user-instances
        """
        user = super().populate_user(request, sociallogin, data)
        if not user.name:
            if name := data.get("name"):
                user.name = name
            elif first_name := data.get("first_name"):
                user.name = first_name
                if last_name := data.get("last_name"):
                    user.name += f" {last_name}"
            else:
                # fallback to the part before @ in the email
                local_part = user.email.split("@")[0]
                user.name = local_part.replace(".", " ").replace("_", " ").title()
        return user

    def pre_social_login(self, request: HttpRequest, sociallogin: SocialLogin) -> None:
        """
        Auto-connects social login to an existing user if emails match.
        Denies login if email is not authorized or user is inactive.
        """
        email = sociallogin.user.email

        if sociallogin.is_existing:
            return

        try:
            user = User.objects.get(email__iexact=email)
            if not user.is_active:
                msg = _("This account has been disabled.")
                raise PermissionDenied(msg)
            # Connect this  account to the existing user
            sociallogin.connect(request, user)

        except User.DoesNotExist as err:
            # Only allow login if the email is pre-authorized
            if not AuthorizedEmail.objects.filter(email__iexact=email).exists():
                msg = _("This email address is not authorized to log in.")
                raise PermissionDenied(msg) from err
