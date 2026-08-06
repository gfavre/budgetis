from io import StringIO

import openpyxl
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from budgetis.accounting.models import GroupResponsibility
from budgetis.accounting.tests.factories import AccountGroupFactory
from budgetis.accounting.tests.factories import GroupResponsibilityFactory
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def _write_excel(tmp_path, rows):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["No", "Compte", "Resp BUD"])
    for row in rows:
        sheet.append(row)
    path = tmp_path / "responsibles.xlsx"
    workbook.save(path)
    return path


def _run(excel_path, year, *, dry_run=False):
    out, err = StringIO(), StringIO()
    call_command(
        "import_group_responsibilities",
        str(excel_path),
        year=year,
        dry_run=dry_run,
        stdout=out,
        stderr=err,
    )
    return out.getvalue(), err.getvalue()


class TestImportGroupResponsibilities:
    def test_raises_when_file_missing(self, tmp_path):
        with pytest.raises(CommandError):
            call_command("import_group_responsibilities", str(tmp_path / "missing.xlsx"), year=2026)

    def test_creates_responsibility_when_none_existed(self, tmp_path):
        group = AccountGroupFactory(code="720")
        user = UserFactory(trigram="ADA")
        excel_path = _write_excel(tmp_path, [["720.351", "Aide sociale", "ADA"]])

        _run(excel_path, 2026)

        responsibility = GroupResponsibility.objects.get(group=group, year=2026)
        assert responsibility.responsible == user

    def test_dry_run_does_not_persist(self, tmp_path):
        AccountGroupFactory(code="720")
        UserFactory(trigram="ADA")
        excel_path = _write_excel(tmp_path, [["720.351", "Aide sociale", "ADA"]])

        _run(excel_path, 2026, dry_run=True)

        assert not GroupResponsibility.objects.exists()

    def test_unchanged_when_already_correct(self, tmp_path):
        user = UserFactory(trigram="ADA")
        group = AccountGroupFactory(code="720")
        GroupResponsibilityFactory(group=group, year=2026, responsible=user)
        excel_path = _write_excel(tmp_path, [["720.351", "Aide sociale", "ADA"]])

        out, _ = _run(excel_path, 2026)

        assert "0 updated, 1 unchanged, 0 skipped" in out

    def test_updates_existing_responsibility(self, tmp_path):
        old_user = UserFactory(trigram="PCO")
        new_user = UserFactory(trigram="ADA")
        group = AccountGroupFactory(code="720")
        GroupResponsibilityFactory(group=group, year=2026, responsible=old_user)
        excel_path = _write_excel(tmp_path, [["720.351", "Aide sociale", "ADA"]])

        _run(excel_path, 2026)

        responsibility = GroupResponsibility.objects.get(group=group, year=2026)
        assert responsibility.responsible == new_user

    def test_skips_unknown_account_group(self, tmp_path):
        UserFactory(trigram="ADA")
        excel_path = _write_excel(tmp_path, [["999.351", "Inconnu", "ADA"]])

        out, err = _run(excel_path, 2026)

        assert not GroupResponsibility.objects.exists()
        assert "0 updated, 0 unchanged, 1 skipped" in out
        assert "999" in err

    def test_skips_unknown_trigram(self, tmp_path):
        AccountGroupFactory(code="720")
        excel_path = _write_excel(tmp_path, [["720.351", "Aide sociale", "XXX"]])

        out, err = _run(excel_path, 2026)

        assert not GroupResponsibility.objects.exists()
        assert "0 updated, 0 unchanged, 1 skipped" in out
        assert "XXX" in err

    def test_ignores_row_with_blank_trigram(self, tmp_path):
        AccountGroupFactory(code="720")
        excel_path = _write_excel(tmp_path, [["720.351", "Aide sociale", None]])

        out, err = _run(excel_path, 2026)

        assert not GroupResponsibility.objects.exists()
        assert "0 updated, 0 unchanged, 0 skipped" in out
        assert err == ""

    def test_skips_conflicting_trigrams_for_same_function(self, tmp_path):
        AccountGroupFactory(code="720")
        UserFactory(trigram="ADA")
        UserFactory(trigram="PCO")
        excel_path = _write_excel(
            tmp_path,
            [
                ["720.351", "Aide sociale", "ADA"],
                ["720.352", "Autre", "PCO"],
            ],
        )

        out, err = _run(excel_path, 2026)

        assert not GroupResponsibility.objects.exists()
        assert "0 updated, 0 unchanged, 0 skipped" in out
        assert "conflicting trigrams" in err
