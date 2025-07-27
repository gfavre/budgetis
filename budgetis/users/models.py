from typing import ClassVar

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CharField
from django.db.models import EmailField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractUser):
    """
    Default custom user model for Budgetis.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    name = CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    email = EmailField(_("email address"), unique=True)
    username = None  # type: ignore[assignment]

    is_municipal = models.BooleanField(default=False)
    trigram = models.CharField(max_length=3, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects: ClassVar[UserManager] = UserManager()

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.id})

    def __str__(self) -> str:
        output = ""
        if self.name:
            output += self.name
        elif getattr(self, "first_name", None) or getattr(self, "last_name", None):
            output += f"{self.first_name or ''} {self.last_name or ''}".strip()
        if output and self.trigram:
            return output + f" ({self.trigram})"
        if self.trigram:
            return self.trigram
        return self.email


class AuthorizedEmail(models.Model):
    email = models.EmailField(unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        editable=False,
        related_name="authorized_emails_created",
    )

    def __str__(self) -> str:
        return self.email
