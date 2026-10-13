from django.conf import settings

from budgetis.users.permissions import can_manage_platform


def allauth_settings(request):
    """Expose some settings from django-allauth in templates."""
    return {
        "ACCOUNT_ALLOW_REGISTRATION": settings.ACCOUNT_ALLOW_REGISTRATION,
        "can_manage_platform": can_manage_platform(request.user),
    }
