import base64
from http import HTTPStatus

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from budgetis.core.models import SiteConfiguration
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db

# A minimal 1x1 PNG - base.html always renders {{ config.logo.url }}, which
# raises if SiteConfiguration has no logo file attached.
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class TestAccountLogoutTemplate:
    def test_uses_the_site_layout(self, client):
        # Regression: allauth/layouts/manage.html used to redefine block main
        # just to re-declare an empty block content, discarding base.html's
        # own container/main-container wrapper (and its navbar) for every
        # "manage" page (logout, change password, sessions...) that doesn't
        # itself override block main.
        SiteConfiguration.objects.get_or_create(
            pk=1, defaults={"logo": SimpleUploadedFile("logo.png", ONE_PIXEL_PNG, content_type="image/png")}
        )
        client.force_login(UserFactory())

        response = client.get(reverse("account_logout"))

        html = response.content.decode()
        assert response.status_code == HTTPStatus.OK
        assert "main-container" in html
        assert "navbar" in html
