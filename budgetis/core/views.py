# core/views.py
from pathlib import Path

from django.http import FileResponse
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import patch_cache_control
from django.views.decorators.cache import cache_page

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


@cache_page(60 * 60 * 24 * 7)  # 1 semaine
def favicon_view(request, size: int):
    config = SiteConfiguration.get_cached()
    path = config.generate_favicon(size)
    if not path:
        msg = "Favicon not available"
        raise Http404(msg)
    file_path = Path(config.logo.storage.path(path))
    response = FileResponse(file_path.open("rb"), content_type="image/png")
    patch_cache_control(response, max_age=60 * 60 * 24)
    return response
