from http import HTTPStatus

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from budgetis.bdi_import.models import AccountImportLog
from budgetis.bdi_import.tests.factories import AccountImportLogFactory
from budgetis.common.models import ChartScheme
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db

LOGIN_URL = "/accounts/login/"


def _uploaded_file():
    return SimpleUploadedFile("budget.xlsx", b"content", content_type="application/vnd.ms-excel")


class TestExcelImportView:
    def test_login_required(self, client):
        response = client.get(reverse("bdi_import:excel-import"))
        assert response.status_code == HTTPStatus.FOUND
        assert LOGIN_URL in response.url

    def test_creates_log_with_excel_kind(self, client):
        client.force_login(UserFactory())

        response = client.post(
            reverse("bdi_import:excel-import"),
            {
                "year": 2027,
                "is_budget": "budget",
                "scheme": ChartScheme.MCH2,
                "account_file": _uploaded_file(),
            },
        )

        log = AccountImportLog.objects.get()
        assert log.kind == AccountImportLog.ImportKind.EXCEL
        assert log.scheme == ChartScheme.MCH2
        assert response.status_code == HTTPStatus.FOUND
        assert response.url == reverse("bdi_import:account-mapping", kwargs={"log_id": log.id})


class TestAccountImportView:
    def test_creates_log_with_bdi_kind(self, client):
        client.force_login(UserFactory())

        client.post(
            reverse("bdi_import:account-import"),
            {
                "year": 2024,
                "is_budget": "actual",
                "scheme": ChartScheme.MCH1,
                "account_file": _uploaded_file(),
            },
        )

        log = AccountImportLog.objects.get()
        assert log.kind == AccountImportLog.ImportKind.BDI
        assert log.scheme == ChartScheme.MCH1


class TestAccountMappingViewRedirect:
    def test_post_redirects_back_to_excel_import_for_an_excel_log(self, client, monkeypatch):
        monkeypatch.setattr("budgetis.bdi_import.views.import_accounts_task.delay", lambda log_id: None)
        client.force_login(UserFactory())
        log = AccountImportLogFactory(kind=AccountImportLog.ImportKind.EXCEL)

        response = client.post(reverse("bdi_import:account-mapping", kwargs={"log_id": log.id}))

        assert response.status_code == HTTPStatus.FOUND
        assert response.url == reverse("bdi_import:excel-import")

    def test_post_redirects_back_to_bdi_import_for_a_bdi_log(self, client, monkeypatch):
        monkeypatch.setattr("budgetis.bdi_import.views.import_accounts_task.delay", lambda log_id: None)
        client.force_login(UserFactory())
        log = AccountImportLogFactory(kind=AccountImportLog.ImportKind.BDI)

        response = client.post(reverse("bdi_import:account-mapping", kwargs={"log_id": log.id}))

        assert response.status_code == HTTPStatus.FOUND
        assert response.url == reverse("bdi_import:account-import")
