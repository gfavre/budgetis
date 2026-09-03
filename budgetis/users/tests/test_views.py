from http import HTTPStatus

import pytest
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.test import RequestFactory
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AccountGroupFactory
from budgetis.accounting.tests.factories import GroupResponsibilityFactory
from budgetis.users.forms import UserAdminChangeForm
from budgetis.users.models import User
from budgetis.users.tests.factories import UserFactory
from budgetis.users.views import UserRedirectView
from budgetis.users.views import UserUpdateView
from budgetis.users.views import user_detail_view


pytestmark = pytest.mark.django_db


class TestUserUpdateView:
    """
    TODO:
        extracting view initialization code as class-scoped fixture
        would be great if only pytest-django supported non-function-scoped
        fixture db access -- this is a work-in-progress for now:
        https://github.com/pytest-dev/pytest-django/pull/258
    """

    def dummy_get_response(self, request: HttpRequest):
        return None

    def test_get_success_url(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")
        request.user = user

        view.request = request
        assert view.get_success_url() == f"/users/{user.pk}/"

    def test_get_object(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")
        request.user = user

        view.request = request

        assert view.get_object() == user

    def test_form_valid(self, user: User, rf: RequestFactory):
        view = UserUpdateView()
        request = rf.get("/fake-url/")

        # Add the session/message middleware to the request
        SessionMiddleware(self.dummy_get_response).process_request(request)
        MessageMiddleware(self.dummy_get_response).process_request(request)
        request.user = user

        view.request = request

        # Initialize the form
        form = UserAdminChangeForm()
        form.cleaned_data = {}
        form.instance = user
        view.form_valid(form)

        messages_sent = [m.message for m in messages.get_messages(request)]
        assert messages_sent == [_("Information successfully updated")]

    def test_updates_trigram(self, client, user: User):
        client.force_login(user)

        client.post(reverse("users:update"), {"name": user.name, "trigram": "ABC"})

        user.refresh_from_db()
        assert user.trigram == "ABC"


class TestUserRedirectView:
    def test_get_redirect_url(self, user: User, rf: RequestFactory):
        view = UserRedirectView()
        request = rf.get("/fake-url")
        request.user = user

        view.request = request
        assert view.get_redirect_url() == f"/users/{user.pk}/"


class TestUserDetailView:
    def test_authenticated(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = UserFactory()
        response = user_detail_view(request, pk=user.pk)

        assert response.status_code == HTTPStatus.OK

    def test_not_authenticated(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = AnonymousUser()
        response = user_detail_view(request, pk=user.pk)
        login_url = reverse(settings.LOGIN_URL)

        assert isinstance(response, HttpResponseRedirect)
        assert response.status_code == HTTPStatus.FOUND
        assert response.url == f"{login_url}?next=/fake-url/"

    def test_own_profile_includes_responsibility_sections(self, client, user: User, site_configuration_with_logo):
        client.force_login(user)

        response = client.get(reverse("users:detail", kwargs={"pk": user.pk}))

        assert "responsibility_sections" in response.context

    def test_other_users_profile_omits_responsibility_sections(self, client, user: User, site_configuration_with_logo):
        client.force_login(UserFactory())

        response = client.get(reverse("users:detail", kwargs={"pk": user.pk}))

        assert "responsibility_sections" not in response.context

    def test_shows_final_accounts_for_the_most_recent_responsibility_year(
        self, client, user: User, site_configuration_with_logo
    ):
        group = AccountGroupFactory(code="720", label="Aide sociale")
        GroupResponsibilityFactory(group=group, year=2027, responsible=user)
        AccountFactory(
            group=group, year=2027, function="720", nature="351", sub_account="", label="Aide sociale individuelle"
        )
        client.force_login(user)

        response = client.get(reverse("users:detail", kwargs={"pk": user.pk}))

        html = response.content.decode()
        assert "720.351" in html
        assert "Aide sociale individuelle" in html

    def test_excludes_accounts_from_older_responsibility_years(self, client, user: User, site_configuration_with_logo):
        group = AccountGroupFactory(code="720", label="Aide sociale")
        GroupResponsibilityFactory(group=group, year=2025, responsible=user)
        GroupResponsibilityFactory(group=group, year=2026, responsible=user)
        AccountFactory(group=group, year=2025, function="720", nature="351", sub_account="", label="Compte 2025")
        AccountFactory(group=group, year=2026, function="720", nature="352", sub_account="", label="Compte 2026")
        client.force_login(user)

        response = client.get(reverse("users:detail", kwargs={"pk": user.pk}))

        html = response.content.decode()
        assert "Compte 2026" in html
        assert "Compte 2025" not in html

    def test_deduplicates_budget_and_actual_variants_of_the_same_account(
        self, client, user: User, site_configuration_with_logo
    ):
        group = AccountGroupFactory(code="720", label="Aide sociale")
        GroupResponsibilityFactory(group=group, year=2026, responsible=user)
        AccountFactory(
            group=group,
            year=2026,
            function="720",
            nature="351",
            sub_account="",
            is_budget=True,
            label="Aide sociale",
        )
        AccountFactory(
            group=group,
            year=2026,
            function="720",
            nature="351",
            sub_account="",
            is_budget=False,
            label="Aide sociale",
        )
        client.force_login(user)

        response = client.get(reverse("users:detail", kwargs={"pk": user.pk}))

        assert response.content.decode().count("720.351") == 1

    def test_shows_section_label_and_view_links(self, client, user: User, site_configuration_with_logo):
        group = AccountGroupFactory(code="720", label="Aide sociale")
        GroupResponsibilityFactory(group=group, year=2027, responsible=user)
        AccountFactory(
            group=group, year=2027, function="720", nature="351", sub_account="", label="Aide sociale individuelle"
        )
        client.force_login(user)

        response = client.get(reverse("users:detail", kwargs={"pk": user.pk}))

        html = response.content.decode()
        assert "720 - Aide sociale" in html
        assert "#group-720" in html
        assert reverse("accounting:account-explorer") in html
        assert reverse("accounting:budget-explorer") in html
