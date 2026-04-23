from http import HTTPStatus

import pytest
from django.urls import reverse

from budgetis.accounting.tests.factories import AccountCommentFactory
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.views.explore import AccountExplorerView
from budgetis.accounting.views.explore import BudgetExplorerView
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db

LOGIN_URL = "/accounts/login/"


# ── Explorer views ──────────────────────────────────────────────────────────


class TestAccountExplorerView:
    def test_login_required(self, client):
        response = client.get(reverse("accounting:account-explorer"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_authenticated_returns_200(self, rf):
        request = rf.get("/")
        request.user = UserFactory()
        response = AccountExplorerView.as_view()(request)
        assert response.status_code == HTTPStatus.OK


class TestBudgetExplorerView:
    def test_login_required(self, client):
        response = client.get(reverse("accounting:budget-explorer"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_authenticated_returns_200(self, rf):
        request = rf.get("/")
        request.user = UserFactory()
        response = BudgetExplorerView.as_view()(request)
        assert response.status_code == HTTPStatus.OK


class TestBudgetByNatureView:
    def test_login_required(self, client):
        response = client.get(reverse("accounting:budget-nature-explorer"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url


class TestAccountByNatureView:
    def test_login_required(self, client):
        response = client.get(reverse("accounting:natures"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url


# ── Comment views ────────────────────────────────────────────────────────────


class TestAccountCommentsView:
    def test_login_required(self, client):
        acc = AccountFactory()
        url = reverse("accounting:account-comments", kwargs={"account_id": acc.id, "kind": "charges"})
        response = client.get(url)
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_returns_200_with_comments_list(self, client):
        user = UserFactory()
        client.force_login(user)
        acc = AccountFactory()
        comment = AccountCommentFactory(account=acc)
        url = reverse("accounting:account-comments", kwargs={"account_id": acc.id, "kind": "charges"})
        response = client.get(url)
        assert response.status_code == HTTPStatus.OK
        assert comment in response.context["comments"]


class TestAccountCommentCreateView:
    def test_login_required(self, client):
        url = reverse("accounting:account-comment-create", kwargs={"account_id": 999, "kind": "charges"})
        response = client.get(url)
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_creates_comment_on_post(self, client):
        user = UserFactory()
        client.force_login(user)
        acc = AccountFactory()
        url = reverse("accounting:account-comment-create", kwargs={"account_id": acc.id, "kind": "charges"})
        client.post(url, {"content": "Test comment"})
        assert acc.comments.filter(content="Test comment").exists()

    def test_returns_htmx_trigger_to_close_modal(self, client):
        user = UserFactory()
        client.force_login(user)
        acc = AccountFactory()
        url = reverse("accounting:account-comment-create", kwargs={"account_id": acc.id, "kind": "charges"})
        response = client.post(url, {"content": "Close trigger test"})
        assert response.status_code == HTTPStatus.OK
        assert response["HX-Trigger"] == "closeAccountCommentsModal"
        assert response["HX-Reswap"] == "none"

    def test_sets_author_from_logged_in_user(self, client):
        user = UserFactory()
        client.force_login(user)
        acc = AccountFactory()
        url = reverse("accounting:account-comment-create", kwargs={"account_id": acc.id, "kind": "charges"})
        client.post(url, {"content": "Author test"})
        comment = acc.comments.get(content="Author test")
        assert comment.author == user


class TestAccountCommentEditView:
    def test_login_required(self, client):
        comment = AccountCommentFactory()
        url = reverse("accounting:account-comment-edit", kwargs={"pk": comment.pk})
        response = client.get(url)
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_post_updates_comment_content(self, client):
        user = UserFactory()
        client.force_login(user)
        comment = AccountCommentFactory(content="old content")
        url = reverse("accounting:account-comment-edit", kwargs={"pk": comment.pk})
        client.post(url, {"content": "new content"})
        comment.refresh_from_db()
        assert comment.content == "new content"


class TestAccountCommentDeleteView:
    def test_login_required(self, client):
        comment = AccountCommentFactory()
        url = reverse("accounting:account-comment-delete", kwargs={"pk": comment.pk})
        response = client.get(url)
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_post_deletes_comment(self, client):
        user = UserFactory()
        client.force_login(user)
        comment = AccountCommentFactory()
        pk = comment.pk
        url = reverse("accounting:account-comment-delete", kwargs={"pk": pk})
        client.post(url)
        from budgetis.accounting.models import AccountComment

        assert not AccountComment.objects.filter(pk=pk).exists()
