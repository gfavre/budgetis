import base64
import re
from decimal import Decimal
from http import HTTPStatus

import pytest
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from budgetis.accounting.tests.factories import AccountCodeMappingFactory
from budgetis.accounting.tests.factories import AccountCommentFactory
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AccountGroupFactory
from budgetis.accounting.tests.factories import AvailableYearFactory
from budgetis.accounting.tests.factories import GroupResponsibilityFactory
from budgetis.accounting.tests.factories import NatureGroupFactory
from budgetis.accounting.views.explore import AccountExplorerView
from budgetis.accounting.views.explore import AccountStagedResultView
from budgetis.accounting.views.explore import BudgetExplorerView
from budgetis.accounting.views.explore import BudgetStagedResultView
from budgetis.common.models import ChartScheme
from budgetis.core.models import SiteConfiguration
from budgetis.finance.models import AvailableYear
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

    def test_hides_prev_actuals_column_across_the_scheme_switch(self, rf):
        AvailableYearFactory(year=2027, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH2)
        AvailableYearFactory(year=2027, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)
        AvailableYearFactory(year=2026, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)
        request = rf.get("/", {"year": 2027})
        request.user = UserFactory()

        response = AccountExplorerView.as_view()(request)

        assert response.context_data["show_col2"] is True
        assert response.context_data["show_col3"] is False

    def test_only_responsible_checkbox_shown_for_a_municipal_user(self, client, site_configuration_with_logo):
        client.force_login(UserFactory(is_municipal=True))

        response = client.get(reverse("accounting:account-explorer"))

        assert 'name="only_responsible"' in response.content.decode()

    def test_only_responsible_checkbox_hidden_for_a_non_municipal_user(self, client, site_configuration_with_logo):
        # GroupResponsibility is a municipal officer's own accounts - a Bourse
        # member has none, so the checkbox would be meaningless for them.
        client.force_login(UserFactory(is_municipal=False))

        response = client.get(reverse("accounting:account-explorer"))

        assert 'name="only_responsible"' not in response.content.decode()

    def test_only_responsible_is_ignored_for_a_non_municipal_user(self, client, site_configuration_with_logo):
        # Even a GroupResponsibility row assigning them, plus a crafted query
        # string, can't turn the filter back on for a non-municipal user.
        user = UserFactory(is_municipal=False)
        client.force_login(user)
        their_group = AccountGroupFactory()
        other_group = AccountGroupFactory()
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.ACTUAL)
        GroupResponsibilityFactory(group=their_group, year=2024, responsible=user)
        their_account = AccountFactory(year=2024, is_budget=False, group=their_group, function="10001", nature="301")
        other_account = AccountFactory(year=2024, is_budget=False, group=other_group, function="20001", nature="301")

        response = client.get(reverse("accounting:account-explorer"), {"year": 2024, "only_responsible": "on"})

        html = response.content.decode()
        assert their_account.full_code in html
        assert other_account.full_code in html

    def test_shows_responsible_trigram_in_parentheses_when_a_group_is_mixed(
        self, client, site_configuration_with_logo
    ):
        # A single AccountGroup can cover several functions (sites/buildings),
        # each with its own responsible - no single name applies to the whole
        # group, so each row must show its own responsible instead (see
        # GroupResponsibility's function-level override).
        client.force_login(UserFactory(is_municipal=True))
        group = AccountGroupFactory()
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.ACTUAL)
        ada = UserFactory(trigram="ADA")
        bob = UserFactory(trigram="BOB")
        GroupResponsibilityFactory(group=group, year=2024, function="72001", responsible=ada)
        GroupResponsibilityFactory(group=group, year=2024, function="72002", responsible=bob)
        AccountFactory(year=2024, is_budget=False, group=group, function="72001", nature="301")
        AccountFactory(year=2024, is_budget=False, group=group, function="72002", nature="301")

        response = client.get(reverse("accounting:account-explorer"), {"year": 2024, "only_responsible": ""})

        html = response.content.decode()
        assert "(ADA)" in html
        assert "(BOB)" in html

    def test_only_responsible_defaults_to_false_for_a_non_municipal_user_with_no_query_string(
        self, client, site_configuration_with_logo
    ):
        # A fresh page load (no query string at all) falls through to the
        # form's own initial-value default, which is True for a municipal
        # user - it must still resolve to False here, unconditionally.
        user = UserFactory(is_municipal=False)
        client.force_login(user)
        their_group = AccountGroupFactory()
        other_group = AccountGroupFactory()
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.ACTUAL)
        GroupResponsibilityFactory(group=their_group, year=2024, responsible=user)
        their_account = AccountFactory(year=2024, is_budget=False, group=their_group, function="10001", nature="301")
        other_account = AccountFactory(year=2024, is_budget=False, group=other_group, function="20001", nature="301")

        response = client.get(reverse("accounting:account-explorer"))

        html = response.content.decode()
        assert their_account.full_code in html
        assert other_account.full_code in html

    def test_nav_dropdowns_link_to_function_nature_and_import_views(self, client):
        client.force_login(UserFactory())
        one_pixel_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        SiteConfiguration.objects.get_or_create(
            pk=1, defaults={"logo": SimpleUploadedFile("logo.png", one_pixel_png, content_type="image/png")}
        )

        response = client.get(reverse("accounting:account-explorer"))

        html = response.content.decode()
        assert reverse("accounting:account-explorer") in html
        assert reverse("accounting:natures") in html
        assert reverse("accounting:account-staged-result") in html
        assert reverse("accounting:budget-explorer") in html
        assert reverse("accounting:budget-nature-explorer") in html
        assert reverse("accounting:budget-staged-result") in html
        assert reverse("bdi_import:account-import") in html
        assert reverse("bdi_import:excel-import") in html


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

    def test_hides_both_comparison_columns_across_the_scheme_switch(self, rf):
        AvailableYearFactory(year=2027, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)
        AvailableYearFactory(year=2026, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)
        AvailableYearFactory(year=2025, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)
        request = rf.get("/", {"year": 2027})
        request.user = UserFactory()

        response = BudgetExplorerView.as_view()(request)

        assert response.context_data["show_col2"] is False
        assert response.context_data["show_col3"] is False

    def test_only_responsible_checkbox_hidden_for_a_non_municipal_user(self, client, site_configuration_with_logo):
        client.force_login(UserFactory(is_municipal=False))

        response = client.get(reverse("accounting:budget-explorer"))

        assert 'name="only_responsible"' not in response.content.decode()


class TestBudgetByNatureView:
    def test_login_required(self, client):
        response = client.get(reverse("accounting:budget-nature-explorer"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_only_responsible_checkbox_not_shown(self, client, site_configuration_with_logo):
        # Every account is grouped by nature code here regardless of who's
        # responsible for it - "only my accounts" has no meaning to filter by.
        client.force_login(UserFactory(is_municipal=True))

        response = client.get(reverse("accounting:budget-nature-explorer"))

        assert 'name="only_responsible"' not in response.content.decode()


class TestAccountByNatureView:
    def test_login_required(self, client):
        response = client.get(reverse("accounting:natures"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_only_responsible_checkbox_not_shown(self, client, site_configuration_with_logo):
        client.force_login(UserFactory(is_municipal=True))

        response = client.get(reverse("accounting:natures"))

        assert 'name="only_responsible"' not in response.content.decode()


class TestBudgetStagedResultView:
    def test_login_required(self, client):
        response = client.get(reverse("accounting:budget-staged-result"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_authenticated_returns_200(self, rf):
        request = rf.get("/")
        request.user = UserFactory()
        response = BudgetStagedResultView.as_view()(request)
        assert response.status_code == HTTPStatus.OK

    def test_shows_comparison_columns_across_the_scheme_switch(self, rf):
        """
        Unlike the detailed explorers, the staged result aggregates by
        two-digit nature group only - a classification stable across the
        MCH1/MCH2 transition - so it keeps comparing across the switch where
        the detailed explorers deliberately stop (see comparison_flags).
        """
        AccountFactory(year=2027, is_budget=True, scheme=ChartScheme.MCH2, nature="3010")
        AccountFactory(year=2026, is_budget=True, scheme=ChartScheme.MCH1, nature="30")
        AccountFactory(year=2025, is_budget=False, scheme=ChartScheme.MCH1, nature="30")
        request = rf.get("/", {"year": 2027})
        request.user = UserFactory()

        response = BudgetStagedResultView.as_view()(request)

        assert response.context_data["show_col2"] is True
        assert response.context_data["show_col3"] is True

    def test_comparison_columns_carry_the_real_prior_year_totals(self, rf):
        """
        Regression guard: an earlier version reused BudgetLoader, which joins
        years by (function, nature, sub_account) - a key that never matches
        across an MCH1/MCH2 scheme change, silently turning every comparison
        column into zeroes instead of the real historical totals.
        """
        AccountFactory(
            year=2027, is_budget=True, scheme=ChartScheme.MCH2, function="30000", nature="3010", charges=Decimal(100)
        )
        AccountFactory(
            year=2026, is_budget=True, scheme=ChartScheme.MCH1, function="300", nature="30", charges=Decimal(500)
        )
        request = rf.get("/", {"year": 2027})
        request.user = UserFactory()

        response = BudgetStagedResultView.as_view()(request)

        assert response.context_data["tiers"][0].col2_charges == Decimal(500)

    def test_only_responsible_checkbox_not_shown(self, client, site_configuration_with_logo):
        # The staged result aggregates the whole commune - "only my
        # accounts" has no meaning there, even for a municipal officer.
        client.force_login(UserFactory(is_municipal=True))

        response = client.get(reverse("accounting:budget-staged-result"))

        assert 'name="only_responsible"' not in response.content.decode()


class TestAccountStagedResultView:
    def test_login_required(self, client):
        response = client.get(reverse("accounting:account-staged-result"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_authenticated_returns_200(self, rf):
        request = rf.get("/")
        request.user = UserFactory()
        response = AccountStagedResultView.as_view()(request)
        assert response.status_code == HTTPStatus.OK

    def test_only_responsible_checkbox_not_shown(self, client, site_configuration_with_logo):
        client.force_login(UserFactory(is_municipal=True))

        response = client.get(reverse("accounting:account-staged-result"))

        assert 'name="only_responsible"' not in response.content.decode()


# ── HTMX partial views ──────────────────────────────────────────────────────
# Each partial's root element id must match its explorer page's hx-target, or
# an htmx outerHTML swap replaces it with a mismatched id - breaking every
# swap after the first, since the original hx-target no longer exists in the
# DOM (regression: budget/budget-by-nature partials used to render
# id="account-list" instead of id="budget-list").


class TestBudgetPartialView:
    def test_login_required(self, client):
        response = client.post(reverse("accounting:budget-partial"), {"year": 2024})
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_root_element_id_matches_explorer_hx_target(self, client):
        client.force_login(UserFactory())
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)

        response = client.post(reverse("accounting:budget-partial"), {"year": 2024})

        assert response.content.decode().strip().startswith('<div id="budget-list">')

    def test_only_responsible_is_ignored_for_a_non_municipal_user(self, client):
        user = UserFactory(is_municipal=False)
        client.force_login(user)
        their_group = AccountGroupFactory()
        other_group = AccountGroupFactory()
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.BUDGET)
        GroupResponsibilityFactory(group=their_group, year=2024, responsible=user)
        their_account = AccountFactory(year=2024, is_budget=True, group=their_group, function="10001", nature="301")
        other_account = AccountFactory(year=2024, is_budget=True, group=other_group, function="20001", nature="301")

        response = client.post(reverse("accounting:budget-partial"), {"year": 2024, "only_responsible": "on"})

        html = response.content.decode()
        assert their_account.full_code in html
        assert other_account.full_code in html

    def test_hx_push_url_reflects_year_and_checked_checkbox(self, client):
        # A page reload, bookmark, or shared link should land back on this
        # same filtered view - see BaseExplorerView.get_context_data, which
        # already restores both from the query string on a plain GET.
        client.force_login(UserFactory(is_municipal=True))
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)

        response = client.post(reverse("accounting:budget-partial"), {"year": 2024, "only_responsible": "on"})

        push_url = response["HX-Push-Url"]
        assert push_url.startswith(reverse("accounting:budget-explorer"))
        assert "year=2024" in push_url
        assert "only_responsible=on" in push_url

    def test_hx_push_url_omits_only_responsible_when_unchecked(self, client):
        client.force_login(UserFactory(is_municipal=True))
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)

        response = client.post(reverse("accounting:budget-partial"), {"year": 2024})

        assert "only_responsible" not in response["HX-Push-Url"]

    def test_hx_push_url_never_includes_only_responsible_for_a_non_municipal_user(self, client):
        client.force_login(UserFactory(is_municipal=False))
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)

        response = client.post(reverse("accounting:budget-partial"), {"year": 2024, "only_responsible": "on"})

        assert "only_responsible" not in response["HX-Push-Url"]


class TestAccountPartialView:
    def test_login_required(self, client):
        response = client.post(reverse("accounting:account-partial"), {"year": 2024})
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_root_element_id_matches_explorer_hx_target(self, client):
        client.force_login(UserFactory())
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)

        response = client.post(reverse("accounting:account-partial"), {"year": 2024})

        assert response.content.decode().strip().startswith('<div id="account-list">')

    def test_hx_push_url_reflects_year_and_checked_checkbox(self, client):
        client.force_login(UserFactory(is_municipal=True))
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)

        response = client.post(reverse("accounting:account-partial"), {"year": 2024, "only_responsible": "on"})

        push_url = response["HX-Push-Url"]
        assert push_url.startswith(reverse("accounting:account-explorer"))
        assert "year=2024" in push_url
        assert "only_responsible=on" in push_url

    def test_hx_push_url_omits_only_responsible_when_unchecked(self, client):
        client.force_login(UserFactory(is_municipal=True))
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)

        response = client.post(reverse("accounting:account-partial"), {"year": 2024})

        assert "only_responsible" not in response["HX-Push-Url"]


class TestBudgetByNaturePartialView:
    def test_login_required(self, client):
        response = client.post(reverse("accounting:budget-nature-partial"), {"year": 2024})
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_root_element_id_matches_explorer_hx_target(self, client):
        client.force_login(UserFactory())
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)

        response = client.post(reverse("accounting:budget-nature-partial"), {"year": 2024})

        assert response.content.decode().strip().startswith('<div id="budget-list">')

    def test_level_3_rows_hidden_by_default(self, client):
        client.force_login(UserFactory())
        AvailableYearFactory(year=2027, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)
        level1 = NatureGroupFactory(level=1, code="3", label="Charges", parent=None)
        level2 = NatureGroupFactory(level=2, code="30", label="Charges de personnel", parent=level1)
        NatureGroupFactory(level=3, code="300", label="Autorités et commissions", parent=level2)
        ag = AccountGroupFactory(scheme=ChartScheme.MCH2)
        AccountFactory(scheme=ChartScheme.MCH2, group=ag, year=2027, is_budget=True, nature="3000")

        response = client.post(reverse("accounting:budget-nature-partial"), {"year": 2027})

        assert "Autorités et commissions" not in response.content.decode()

    def test_level_3_rows_shown_when_detail_checked(self, client):
        client.force_login(UserFactory())
        AvailableYearFactory(year=2027, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)
        level1 = NatureGroupFactory(level=1, code="3", label="Charges", parent=None)
        level2 = NatureGroupFactory(level=2, code="30", label="Charges de personnel", parent=level1)
        NatureGroupFactory(level=3, code="300", label="Autorités et commissions", parent=level2)
        ag = AccountGroupFactory(scheme=ChartScheme.MCH2)
        AccountFactory(scheme=ChartScheme.MCH2, group=ag, year=2027, is_budget=True, nature="3000")

        response = client.post(reverse("accounting:budget-nature-partial"), {"year": 2027, "detail": "on"})

        assert "Autorités et commissions" in response.content.decode()


class TestBudgetStagedResultPartialView:
    def test_login_required(self, client):
        response = client.post(reverse("accounting:budget-staged-partial"), {"year": 2024})
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_root_element_id_matches_explorer_hx_target(self, client):
        client.force_login(UserFactory())
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)

        response = client.post(reverse("accounting:budget-staged-partial"), {"year": 2024})

        assert response.content.decode().strip().startswith('<div id="staged-result">')


class TestAccountStagedResultPartialView:
    def test_login_required(self, client):
        response = client.post(reverse("accounting:account-staged-partial"), {"year": 2024})
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_root_element_id_matches_explorer_hx_target(self, client):
        client.force_login(UserFactory())
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)

        response = client.post(reverse("accounting:account-staged-partial"), {"year": 2024})

        assert response.content.decode().strip().startswith('<div id="staged-result">')


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


# ── History modal ────────────────────────────────────────────────────────────

TRANSITION_YEAR = 2027
PRE_TRANSITION_YEAR = 2026


def _history_url(account):
    return reverse("accounting:account-history", kwargs={"account_id": account.id})


def _set_up_transition_years():
    AvailableYearFactory(year=PRE_TRANSITION_YEAR, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH1)
    AvailableYearFactory(year=PRE_TRANSITION_YEAR, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH1)
    AvailableYearFactory(year=TRANSITION_YEAR, type=AvailableYear.YearType.BUDGET, scheme=ChartScheme.MCH2)
    AvailableYearFactory(year=TRANSITION_YEAR, type=AvailableYear.YearType.ACTUAL, scheme=ChartScheme.MCH2)


class TestAccountHistoryModal:
    def test_login_required(self, client):
        account = AccountFactory()
        response = client.get(_history_url(account))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_mch1_account_is_unaffected(self, client):
        client.force_login(UserFactory())
        AccountFactory(
            scheme=ChartScheme.MCH1,
            year=2025,
            function="100",
            nature="301",
            sub_account="",
            is_budget=False,
            charges=Decimal("500"),
        )
        account = AccountFactory(
            scheme=ChartScheme.MCH1,
            year=2026,
            function="100",
            nature="301",
            sub_account="",
            is_budget=False,
            charges=Decimal("700"),
        )

        response = client.get(_history_url(account))

        assert response.status_code == HTTPStatus.OK
        assert response.context["years"] == "[2025, 2026]"
        assert response.context["comptes"] == "[500.0, 700.0]"

    def test_one_to_one_bridges_the_scheme_switch(self, client):
        client.force_login(UserFactory())
        _set_up_transition_years()
        AccountCodeMappingFactory(
            mch1_function="100",
            mch1_nature="301",
            mch1_sub_account="",
            mch2_function="01100",
            mch2_nature="3010",
            mch2_sub_account="",
        )
        AccountFactory(
            scheme=ChartScheme.MCH1,
            year=PRE_TRANSITION_YEAR,
            function="100",
            nature="301",
            sub_account="",
            label="Salaire des autorités et commissions - scrt.",
            is_budget=False,
            charges=Decimal("500"),
        )
        account = AccountFactory(
            scheme=ChartScheme.MCH2,
            year=TRANSITION_YEAR,
            function="01100",
            nature="3010",
            sub_account="",
            is_budget=False,
            charges=Decimal("700"),
        )

        response = client.get(_history_url(account))

        assert response.context["comptes"] == "[500.0, 700.0]"
        assert response.context["transition_year"] == TRANSITION_YEAR
        assert response.context["split_origins"] == []
        assert response.context["pre_mch2_origins"] == [
            {
                "function": "100",
                "nature": "301",
                "sub_account": "",
                "code": "100.301",
                "label": "Salaire des autorités et commissions - scrt.",
            }
        ]

    def test_actuals_gap_when_not_yet_recorded_while_budget_continues(self, client):
        # Actuals lag behind budget: a year with a budget row but no actuals
        # row yet must show a gap on the "comptes" line, not a false zero,
        # while the budget line keeps going.
        client.force_login(UserFactory())
        _set_up_transition_years()
        AccountCodeMappingFactory(
            mch1_function="100",
            mch1_nature="301",
            mch1_sub_account="",
            mch2_function="01100",
            mch2_nature="3010",
            mch2_sub_account="",
        )
        AccountFactory(
            scheme=ChartScheme.MCH1,
            year=PRE_TRANSITION_YEAR,
            function="100",
            nature="301",
            sub_account="",
            is_budget=False,
            charges=Decimal("500"),
        )
        account = AccountFactory(
            scheme=ChartScheme.MCH2,
            year=TRANSITION_YEAR,
            function="01100",
            nature="3010",
            sub_account="",
            is_budget=True,
            charges=Decimal("700"),
        )

        response = client.get(_history_url(account))

        assert response.context["comptes"] == "[500.0, null]"
        assert response.context["budgets"] == "[0.0, 700.0]"

    def test_merge_sums_origins_before_the_transition(self, client):
        client.force_login(UserFactory())
        _set_up_transition_years()
        AccountCodeMappingFactory(
            mch1_function="110",
            mch1_nature="318",
            mch1_sub_account="",
            mch2_function="96900",
            mch2_nature="3420",
            mch2_sub_account="",
        )
        AccountCodeMappingFactory(
            mch1_function="220",
            mch1_nature="318",
            mch1_sub_account="",
            mch2_function="96900",
            mch2_nature="3420",
            mch2_sub_account="",
        )
        AccountFactory(
            scheme=ChartScheme.MCH1,
            year=PRE_TRANSITION_YEAR,
            function="110",
            nature="318",
            sub_account="",
            is_budget=False,
            charges=Decimal("300"),
        )
        AccountFactory(
            scheme=ChartScheme.MCH1,
            year=PRE_TRANSITION_YEAR,
            function="220",
            nature="318",
            sub_account="",
            is_budget=False,
            charges=Decimal("400"),
        )
        account = AccountFactory(
            scheme=ChartScheme.MCH2,
            year=TRANSITION_YEAR,
            function="96900",
            nature="3420",
            sub_account="",
            is_budget=False,
            charges=Decimal("900"),
        )

        response = client.get(_history_url(account))

        assert response.context["comptes"] == "[700.0, 900.0]"
        assert response.context["split_origins"] == []
        codes = sorted(entry["code"] for entry in response.context["pre_mch2_origins"])
        assert codes == ["110.318", "220.318"]

    def test_split_has_no_pre_transition_data_and_lists_origins(self, client):
        client.force_login(UserFactory())
        _set_up_transition_years()
        AccountCodeMappingFactory(
            mch1_function="100",
            mch1_nature="306",
            mch1_sub_account="",
            mch2_function="01100",
            mch2_nature="3049",
            mch2_sub_account="",
        )
        AccountCodeMappingFactory(
            mch1_function="100",
            mch1_nature="306",
            mch1_sub_account="",
            mch2_function="01100",
            mch2_nature="3099",
            mch2_sub_account="",
        )
        AccountFactory(
            scheme=ChartScheme.MCH1,
            year=PRE_TRANSITION_YEAR,
            function="100",
            nature="306",
            sub_account="",
            label="Conseil Communal - Frais",
            is_budget=False,
            charges=Decimal("300"),
        )
        account = AccountFactory(
            scheme=ChartScheme.MCH2,
            year=TRANSITION_YEAR,
            function="01100",
            nature="3049",
            sub_account="",
            is_budget=False,
            charges=Decimal("120"),
        )
        AccountFactory(
            scheme=ChartScheme.MCH2,
            year=TRANSITION_YEAR,
            function="01100",
            nature="3099",
            sub_account="",
            label="Autres charges du personnel",
            is_budget=False,
            charges=Decimal("0"),
        )

        response = client.get(_history_url(account))

        assert response.context["comptes"] == "[null, 120.0]"
        assert response.context["pre_mch2_origins"] == []
        split_origins = response.context["split_origins"]
        assert len(split_origins) == 1
        assert split_origins[0]["code"] == "100.306"
        assert split_origins[0]["label"] == "Conseil Communal - Frais"
        assert split_origins[0]["other_targets"] == [{"code": "01100.3099", "label": "Autres charges du personnel"}]

    def test_new_account_has_no_origins_and_no_pre_transition_data(self, client):
        client.force_login(UserFactory())
        _set_up_transition_years()
        account = AccountFactory(
            scheme=ChartScheme.MCH2,
            year=TRANSITION_YEAR,
            function="93000",
            nature="3622",
            sub_account="",
            is_budget=False,
            charges=Decimal("50"),
        )

        response = client.get(_history_url(account))

        assert response.context["comptes"] == "[0.0, 50.0]"
        assert response.context["pre_mch2_origins"] == []
        assert response.context["split_origins"] == []


# ── In-place budget amount editing ──────────────────────────────────────────


def _grant_change_account(user):
    permission = Permission.objects.get(codename="change_account", content_type__app_label="accounting")
    user.user_permissions.add(permission)


def _amount_edit_url(account, kind):
    return reverse("accounting:account-amount-edit", args=[account.pk, kind])


class TestAccountAmountEditView:
    def test_login_required(self, client):
        account = AccountFactory(is_budget=True)
        response = client.get(_amount_edit_url(account, "charges"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_authenticated_without_permission_is_forbidden(self, client, site_configuration_with_logo):
        client.force_login(UserFactory())
        account = AccountFactory(is_budget=True)

        response = client.get(_amount_edit_url(account, "charges"))

        assert response.status_code == HTTPStatus.FORBIDDEN

    def test_get_returns_form_prefilled_with_current_amount(self, client):
        user = UserFactory()
        _grant_change_account(user)
        client.force_login(user)
        account = AccountFactory(is_budget=True, charges=Decimal("1234.50"))

        response = client.get(_amount_edit_url(account, "charges"))

        assert response.status_code == HTTPStatus.OK
        assert response.context["form"].initial["amount"] == Decimal("1234.50")

    def test_edit_form_includes_a_csrf_token_htmx_can_post_back(self, site_configuration_with_logo):
        """
        The input posts via hx-post directly on itself (no <form>), so
        Django's test Client - which skips CSRF enforcement by default -
        can't catch a missing/unreachable token the way a real browser
        would. Enforce it here to prove the rendered csrfmiddlewaretoken
        input is both present and actually usable for the POST htmx sends.
        """
        client = Client(enforce_csrf_checks=True)
        user = UserFactory()
        _grant_change_account(user)
        client.force_login(user)
        account = AccountFactory(is_budget=True, charges=Decimal("100.00"))

        form_response = client.get(_amount_edit_url(account, "charges"))
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form_response.content.decode())
        assert match, "expected a csrfmiddlewaretoken input in the rendered edit form"

        response = client.post(
            _amount_edit_url(account, "charges"), {"amount": "250.00", "csrfmiddlewaretoken": match[1]}
        )

        assert response.status_code == HTTPStatus.OK
        account.refresh_from_db()
        assert account.charges == Decimal("250.00")

    def test_unknown_kind_is_not_found(self, client, site_configuration_with_logo):
        user = UserFactory()
        _grant_change_account(user)
        client.force_login(user)
        account = AccountFactory(is_budget=True)

        response = client.get(_amount_edit_url(account, "not-a-kind"))

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_actuals_account_is_not_editable(self, client, site_configuration_with_logo):
        user = UserFactory()
        _grant_change_account(user)
        client.force_login(user)
        account = AccountFactory(is_budget=False)

        response = client.get(_amount_edit_url(account, "charges"))

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_post_saves_charges_and_returns_display_cell(self, client):
        user = UserFactory()
        _grant_change_account(user)
        client.force_login(user)
        account = AccountFactory(is_budget=True, charges=Decimal("100.00"), revenues=Decimal("0.00"))

        response = client.post(_amount_edit_url(account, "charges"), {"amount": "2500.75"})

        assert response.status_code == HTTPStatus.OK
        account.refresh_from_db()
        assert account.charges == Decimal("2500.75")
        assert f'id="amount-cell-{account.pk}-charges"' in response.content.decode()

    def test_post_saves_revenues_without_touching_charges(self, client):
        user = UserFactory()
        _grant_change_account(user)
        client.force_login(user)
        account = AccountFactory(is_budget=True, charges=Decimal("100.00"), revenues=Decimal("0.00"))

        response = client.post(_amount_edit_url(account, "revenues"), {"amount": "42.00"})

        assert response.status_code == HTTPStatus.OK
        account.refresh_from_db()
        assert account.revenues == Decimal("42.00")
        assert account.charges == Decimal("100.00")

    def test_post_invalid_amount_returns_error_without_saving(self, client):
        user = UserFactory()
        _grant_change_account(user)
        client.force_login(user)
        account = AccountFactory(is_budget=True, charges=Decimal("100.00"))

        response = client.post(_amount_edit_url(account, "charges"), {"amount": "not-a-number"})

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        account.refresh_from_db()
        assert account.charges == Decimal("100.00")

    def test_post_without_permission_is_forbidden_and_does_not_save(self, client, site_configuration_with_logo):
        client.force_login(UserFactory())
        account = AccountFactory(is_budget=True, charges=Decimal("100.00"))

        response = client.post(_amount_edit_url(account, "charges"), {"amount": "9999.00"})

        assert response.status_code == HTTPStatus.FORBIDDEN
        account.refresh_from_db()
        assert account.charges == Decimal("100.00")


class TestBudgetExplorerAmountEditability:
    def test_editable_cell_shown_for_user_with_permission(self, client, site_configuration_with_logo):
        user = UserFactory()
        _grant_change_account(user)
        client.force_login(user)
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.BUDGET)
        account = AccountFactory(is_budget=True, year=2024, group=AccountGroupFactory(level=1, parent=None))

        response = client.get(reverse("accounting:budget-explorer"), {"year": 2024, "only_responsible": ""})

        assert f'id="amount-cell-{account.pk}-charges"' in response.content.decode()

    def test_plain_cell_shown_for_user_without_permission(self, client, site_configuration_with_logo):
        client.force_login(UserFactory())
        AvailableYearFactory(year=2024, type=AvailableYear.YearType.BUDGET)
        account = AccountFactory(is_budget=True, year=2024, group=AccountGroupFactory(level=1, parent=None))

        response = client.get(reverse("accounting:budget-explorer"), {"year": 2024, "only_responsible": ""})

        assert f'id="amount-cell-{account.pk}-charges"' not in response.content.decode()
