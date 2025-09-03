from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import AuthorizedEmail
from .models import User


if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    list_display = ["email", "name", "trigram", "is_municipal", "is_superuser"]
    search_fields = ["email", "name", "trigram"]
    ordering = ["id"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("name", "trigram", "is_municipal")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    # add form : sans mot de passe pour municipaux
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "name", "trigram", "is_municipal", "is_staff", "is_superuser"),
            },
        ),
    )

    def save_model(self, request, obj: User, form, change):
        """Met un mot de passe inutilisable pour municipaux créés dans l’admin."""
        if not change:
            if obj.is_municipal and not obj.is_superuser and not obj.is_staff:
                obj.set_unusable_password()
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return True

    def delete_model(self, request, obj):
        obj.delete()


@admin.register(AuthorizedEmail)
class AuthorizedEmailAdmin(admin.ModelAdmin):
    list_display = ("email", "created_by")
    readonly_fields = ("created_by",)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
