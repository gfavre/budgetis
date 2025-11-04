from allauth.account.forms import SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django import forms
from django.contrib.auth import forms as admin_forms
from django.forms import EmailField
from django.utils.translation import gettext_lazy as _

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
