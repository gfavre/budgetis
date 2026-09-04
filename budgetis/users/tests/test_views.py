from http import HTTPStatus

import pytest
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
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
from budgetis.users.models import BOURSE_GROUP_NAME
from budgetis.users.models import User
from budgetis.users.tests.factories import UserFactory
from budgetis.users.views import UserRedirectView
from budgetis.users.views import UserUpdateView
from budgetis.users.views import user_detail_view


pytestmark = pytest.mark.django_db


def _grant(user, codename, app_label):
    permission = Permission.objects.get(codename=codename, content_type__app_label=app_label)
    user.user_permissions.add(permission)


def _management_url():
    return reverse("users:management")


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


class TestUserManagementView:
    def test_anonymous_user_is_redirected_to_login(self, client):
        response = client.get(_management_url())

        login_url = reverse(settings.LOGIN_URL)
        assert response.status_code == HTTPStatus.FOUND
        assert response.url == f"{login_url}?next={_management_url()}"

    def test_user_with_neither_permission_gets_forbidden(self, client, user: User):
        client.force_login(user)

        response = client.get(_management_url())

        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_user_with_only_invite_permission_sees_only_that_section(self, client, user: User):
        _grant(user, "add_user", "users")
        client.force_login(user)

        response = client.get(_management_url())

        assert response.status_code == HTTPStatus.OK
        assert response.context["can_invite"] is True
        assert response.context["can_nominate"] is False

    def test_user_with_only_nominate_permission_sees_only_that_section(self, client, user: User):
        _grant(user, "change_group", "auth")
        client.force_login(user)

        response = client.get(_management_url())

        assert response.status_code == HTTPStatus.OK
        assert response.context["can_invite"] is False
        assert response.context["can_nominate"] is True

    def test_invite_creates_a_user(self, client, user: User):
        _grant(user, "add_user", "users")
        client.force_login(user)

        response = client.post(
            _management_url(),
            {
                "invite_submit": "1",
                "email": "future@example.com",
                "name": "Future Municipal",
                "trigram": "FUT",
            },
        )

        assert response.status_code == HTTPStatus.FOUND
        assert User.objects.filter(email="future@example.com").exists()

    def test_invite_without_permission_is_forbidden_and_does_not_create_a_user(self, client, user: User):
        _grant(user, "change_group", "auth")
        client.force_login(user)

        response = client.post(
            _management_url(),
            {
                "invite_submit": "1",
                "email": "future@example.com",
                "name": "Future Municipal",
                "trigram": "FUT",
            },
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert not User.objects.filter(email="future@example.com").exists()

    def test_nominate_adds_an_existing_user_to_the_bourse_group(self, client, user: User):
        _grant(user, "change_group", "auth")
        client.force_login(user)
        candidate = UserFactory()

        response = client.post(_management_url(), {"nominate_submit": "1", "user": candidate.pk})

        assert response.status_code == HTTPStatus.FOUND
        assert candidate.groups.filter(name=BOURSE_GROUP_NAME).exists()

    def test_nominate_without_permission_is_forbidden_and_does_not_change_groups(self, client, user: User):
        _grant(user, "add_user", "users")
        client.force_login(user)
        candidate = UserFactory()

        response = client.post(_management_url(), {"nominate_submit": "1", "user": candidate.pk})

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert not candidate.groups.filter(name=BOURSE_GROUP_NAME).exists()

    def test_bourse_members_are_listed(self, client, user: User):
        _grant(user, "change_group", "auth")
        client.force_login(user)
        bourse = Group.objects.create(name=BOURSE_GROUP_NAME)
        member = UserFactory(name="Existing Member")
        member.groups.add(bourse)

        response = client.get(_management_url())

        assert member in response.context["bourse_members"]


class TestUserManagementNavLink:
    """The "Users" nav link (base.html) must only appear for users who can act on that page."""

    def test_regular_user_does_not_see_the_nav_link(self, client, user: User, site_configuration_with_logo):
        client.force_login(user)

        response = client.get(reverse("users:detail", kwargs={"pk": user.pk}))

        assert _management_url() not in response.content.decode()

    def test_admin_sees_the_nav_link(self, client, user: User, site_configuration_with_logo):
        _grant(user, "add_user", "users")
        client.force_login(user)

        response = client.get(reverse("users:detail", kwargs={"pk": user.pk}))

        assert _management_url() in response.content.decode()

    def test_bourse_member_sees_the_nav_link(self, client, user: User, site_configuration_with_logo):
        _grant(user, "change_group", "auth")
        client.force_login(user)

        response = client.get(reverse("users:detail", kwargs={"pk": user.pk}))

        assert _management_url() in response.content.decode()

    def test_regular_user_does_not_see_the_django_admin_link(self, client, user: User, site_configuration_with_logo):
        client.force_login(user)

        response = client.get(reverse("users:detail", kwargs={"pk": user.pk}))

        assert reverse("admin:index") not in response.content.decode()

    def test_staff_user_sees_the_django_admin_link(self, client, user: User, site_configuration_with_logo):
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        client.force_login(user)

        response = client.get(reverse("users:detail", kwargs={"pk": user.pk}))

        assert reverse("admin:index") in response.content.decode()
