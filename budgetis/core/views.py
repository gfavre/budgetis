# core/views.py
from django.shortcuts import render
from django.urls import reverse

from .models import SiteConfiguration


def home_view(request):
    config = SiteConfiguration.get_cached()
    if not request.user.is_authenticated:
        return render(
            request,
            "core/home_public.html",
            {
                "logo": config.logo,
                "commune_name": config.commune_name,
                "login_url": reverse("microsoft_login"),
            },
        )

    return render(
        request,
        "core/home.html",
        {
            "logo": config.logo,
            "commune_name": config.commune_name,
            "login_url": reverse("microsoft_login"),
        },
    )
