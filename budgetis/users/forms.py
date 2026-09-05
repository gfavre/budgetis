from typing import cast

from allauth.account.forms import SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django import forms
from django.contrib.auth import forms as admin_forms
from django.contrib.auth.models import Group
from django.forms import EmailField
from django.utils.translation import gettext_lazy as _

from .models import BOURSE_GROUP_NAME
from .models import User


class UserAdminChangeForm(admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):  # type: ignore[name-defined]
        model = User
        field_classes = {"email": EmailField}


class UserAdminCreationForm(forms.ModelForm):
    """
    Formulaire de création utilisateur pour l'admin.
    - Admins/superadmins : demande un mot de passe.
    - Municipaux : pas de mot de passe (il est unusable automatiquement).
    """

    password1 = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput,
        required=False,
    )
    password2 = forms.CharField(
        label=_("Password confirmation"),
        widget=forms.PasswordInput,
        required=False,
    )

    class Meta:
        model = User
        fields = ("email", "name", "trigram", "is_municipal", "is_staff", "is_superuser")

    def clean(self):
        cleaned_data = super().clean()
        is_municipal = cleaned_data.get("is_municipal", False)
        is_staff = cleaned_data.get("is_staff", False)
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if not is_municipal and is_staff:
            # Admin : mot de passe requis
            if not password1 or not password2:
                raise forms.ValidationError(_("Password is required for admins."))
            if password1 != password2:
                raise forms.ValidationError(_("Passwords don't match."))
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        if not self.cleaned_data.get("is_staff") or not self.cleaned_data.get("is_superuser"):
            user.set_unusable_password()
        else:
            user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserInviteForm(forms.ModelForm):
    """
    Creates a new account for someone who hasn't signed in yet - no password
    field: sign-in is Microsoft SSO only (see MunicipalSocialAccountAdapter),
    and the account activates itself the first time that email logs in
    there. `is_staff`/`is_superuser` are deliberately not exposed here (only
    via Django admin) - an account created this way can never be an admin.
    """

    add_to_bourse = forms.BooleanField(
        label=_("Add to the Bourse group"),
        required=False,
        help_text=_("Grants access to budget editing and Sankey configuration."),
    )

    class Meta:
        model = User
        fields = ("email", "name", "trigram", "is_municipal")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_unusable_password()
        if commit:
            user.save()
            if self.cleaned_data["add_to_bourse"]:
                bourse, _created = Group.objects.get_or_create(name=BOURSE_GROUP_NAME)
                user.groups.add(bourse)
        return user


class BourseNominationForm(forms.Form):
    """Adds an existing user to the Bourse group - see BOURSE_GROUP_NAME."""

    user = forms.ModelChoiceField(
        label=_("User"),
        queryset=User.objects.none(),  # set in __init__, needs the DB
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = (
            User.objects.filter(is_active=True).exclude(groups__name=BOURSE_GROUP_NAME).order_by("trigram", "name")
        )
        field = cast("forms.ModelChoiceField", self.fields["user"])
        field.queryset = queryset
        # Not `= str` directly: django-stubs types label_from_instance as a
        # bound method, so mypy flags a plain callable reassignment
        # (method-assign) unless it's wrapped in a lambda.
        field.label_from_instance = lambda obj: str(obj)  # noqa: PLW0108

    def save(self):
        bourse, _created = Group.objects.get_or_create(name=BOURSE_GROUP_NAME)
        self.cleaned_data["user"].groups.add(bourse)


class DeactivateUserForm(forms.Form):
    """
    Deactivates an existing user account - admin-only (`users.change_user`,
    unlike Bourse co-optation which only needs `auth.change_group`). The
    requesting user is excluded from the choices so an admin can't lock
    themselves out from this page.
    """

    user = forms.ModelChoiceField(
        label=_("User"),
        queryset=User.objects.none(),  # set in __init__, needs the DB
    )

    def __init__(self, *args, requesting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = User.objects.filter(is_active=True)
        if requesting_user is not None:
            queryset = queryset.exclude(pk=requesting_user.pk)
        field = cast("forms.ModelChoiceField", self.fields["user"])
        field.queryset = queryset.order_by("trigram", "name")
        field.label_from_instance = lambda obj: str(obj)  # noqa: PLW0108

    def save(self):
        user = self.cleaned_data["user"]
        user.is_active = False
        user.save(update_fields=["is_active"])
        return user


class ReactivateUserForm(forms.Form):
    """Reactivates a previously deactivated user account - admin-only (`users.change_user`), see DeactivateUserForm."""

    user = forms.ModelChoiceField(
        label=_("User"),
        queryset=User.objects.none(),  # set in __init__, needs the DB
    )

    def __init__(self, *args, requesting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = User.objects.filter(is_active=False)
        if requesting_user is not None:
            queryset = queryset.exclude(pk=requesting_user.pk)
        field = cast("forms.ModelChoiceField", self.fields["user"])
        field.queryset = queryset.order_by("trigram", "name")
        field.label_from_instance = lambda obj: str(obj)  # noqa: PLW0108

    def save(self):
        user = self.cleaned_data["user"]
        user.is_active = True
        user.save(update_fields=["is_active"])
        return user


class UserEditForm(forms.ModelForm):
    """Admin-only edit of another user's basic profile fields - see UserAdminUpdateView."""

    class Meta:
        model = User
        fields = ("name", "trigram", "is_municipal")


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("name", "trigram")


class UserSignupForm(SignupForm):
    """
    Form that will be rendered on a user sign up section/screen.
    Default fields will be added automatically.
    Check UserSocialSignupForm for accounts created from social.
    """


class UserSocialSignupForm(SocialSignupForm):
    """
    Renders the form when user has signed up using social accounts.
    Default fields will be added automatically.
    See UserSignupForm otherwise.
    """
