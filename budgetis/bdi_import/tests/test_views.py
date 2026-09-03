from http import HTTPStatus

import openpyxl
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from budgetis.bdi_import.models import AccountImportLog
from budgetis.bdi_import.models import ColumnMapping
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


def _write_mapping_preview_excel(tmp_path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Code", "Libellé", "Charges", "Revenus"])
    sheet.append(["720.351", "Aide sociale", 1000, 500])
    path = tmp_path / "preview.xlsx"
    workbook.save(path)
    return path


class TestAccountMappingViewGet:
    def test_shows_sample_values_per_column(self, client, tmp_path, site_configuration_with_logo):
        client.force_login(UserFactory())
        excel_path = _write_mapping_preview_excel(tmp_path)
        with excel_path.open("rb") as fh:
            log = AccountImportLogFactory(
                file=SimpleUploadedFile("preview.xlsx", fh.read(), content_type="application/vnd.ms-excel")
            )

        response = client.get(reverse("bdi_import:account-mapping", kwargs={"log_id": log.id}))

        assert response.status_code == HTTPStatus.OK
        assert response.context["column_samples"]["Code"] == ["720.351"]
        html = response.content.decode()
        assert "Aide sociale" in html
        assert "column_map[Code]" in html


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


class TestAccountMappingViewColumnMapping:
    def test_total_field_is_always_derived_from_total_even_without_a_checkbox(self, client, monkeypatch):
        # Regression: a separate "derive from total" checkbox used to be
        # required alongside picking the "Total (signed)" field, and forgetting
        # it silently zeroed every amount. The field itself now always implies it.
        monkeypatch.setattr("budgetis.bdi_import.views.import_accounts_task.delay", lambda log_id: None)
        client.force_login(UserFactory())
        log = AccountImportLogFactory()

        client.post(
            reverse("bdi_import:account-mapping", kwargs={"log_id": log.id}),
            {"column_map[Budget 2027]": ColumnMapping.Field.TOTAL},
        )

        mapping = ColumnMapping.objects.get(log=log, field=ColumnMapping.Field.TOTAL)
        assert mapping.derived_from_total is True
