from http import HTTPStatus

import pytest
from django.urls import reverse

from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


class TestAccountLogoutTemplate:
    def test_uses_the_site_layout(self, client, site_configuration_with_logo):
        # Regression: allauth/layouts/manage.html used to redefine block main
        # just to re-declare an empty block content, discarding base.html's
        # own container/main-container wrapper (and its navbar) for every
        # "manage" page (logout, change password, sessions...) that doesn't
        # itself override block main.
        client.force_login(UserFactory())

        response = client.get(reverse("account_logout"))

        html = response.content.decode()
        assert response.status_code == HTTPStatus.OK
        assert "main-container" in html
        assert "navbar" in html
