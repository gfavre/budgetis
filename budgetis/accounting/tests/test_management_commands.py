from io import StringIO

import openpyxl
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from budgetis.accounting.management.commands.import_mch2_functional_classification import DEFAULT_EXCEL_PATH
from budgetis.accounting.models import AccountGroup
from budgetis.accounting.models import GroupResponsibility
from budgetis.accounting.tests.factories import AccountGroupFactory
from budgetis.accounting.tests.factories import GroupResponsibilityFactory
from budgetis.common.models import ChartScheme
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


def _write_classification_excel(tmp_path, rows):
    """`rows` are (n1, n2, n3, n4, label) tuples, as they appear in the source sheet."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Classification fonctionnelle"
    sheet.append(["Fonction : Niveau", None, None, None, "Désignation"])
    sheet.append(["N1", "N2", "N3", "N4", None])
    sheet.append(["CLASSIFICATION FONCTIONNELLE", None, None, None, None])
    for row in rows:
        sheet.append(row)
    path = tmp_path / "classification.xlsx"
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


def _run_classification(excel_path, *, dry_run=False):
    out, err = StringIO(), StringIO()
    call_command(
        "import_mch2_functional_classification",
        str(excel_path),
        dry_run=dry_run,
        stdout=out,
        stderr=err,
    )
    return out.getvalue(), err.getvalue()


class TestImportMch2FunctionalClassification:
    def test_raises_when_file_missing(self, tmp_path):
        with pytest.raises(CommandError):
            call_command("import_mch2_functional_classification", str(tmp_path / "missing.xlsx"))

    def test_builds_four_level_hierarchy(self, tmp_path):
        excel_path = _write_classification_excel(
            tmp_path,
            [
                (0, None, None, None, "Administration générale"),
                (None, "01", None, None, "Législatif et exécutif"),
                (None, None, "011", None, "Législatif"),
                (None, None, None, "0110", "Législatif"),
            ],
        )

        out, _ = _run_classification(excel_path)

        assert "4 created, 0 updated, 0 unchanged" in out
        n1 = AccountGroup.objects.get(scheme=ChartScheme.MCH2, level=1, code="0")
        n2 = AccountGroup.objects.get(scheme=ChartScheme.MCH2, level=2, code="01")
        n3 = AccountGroup.objects.get(scheme=ChartScheme.MCH2, level=3, code="011")
        n4 = AccountGroup.objects.get(scheme=ChartScheme.MCH2, level=4, code="0110")
        assert n2.parent == n1
        assert n3.parent == n2
        assert n4.parent == n3
        assert n4.label == "Législatif"

    def test_dry_run_does_not_persist(self, tmp_path):
        excel_path = _write_classification_excel(tmp_path, [(0, None, None, None, "Administration générale")])

        _run_classification(excel_path, dry_run=True)

        assert not AccountGroup.objects.filter(scheme=ChartScheme.MCH2).exists()

    def test_rerun_is_unchanged(self, tmp_path):
        excel_path = _write_classification_excel(tmp_path, [(0, None, None, None, "Administration générale")])
        _run_classification(excel_path)

        out, _ = _run_classification(excel_path)

        assert "0 created, 0 updated, 1 unchanged" in out

    def test_rerun_updates_changed_label(self, tmp_path):
        excel_path = _write_classification_excel(tmp_path, [(0, None, None, None, "Administration générale")])
        _run_classification(excel_path)
        renamed_path = _write_classification_excel(tmp_path, [(0, None, None, None, "Administration générale bis")])

        out, _ = _run_classification(renamed_path)

        assert "0 created, 1 updated, 0 unchanged" in out
        group = AccountGroup.objects.get(scheme=ChartScheme.MCH2, level=1, code="0")
        assert group.label == "Administration générale bis"

    def test_does_not_touch_mch1_groups(self, tmp_path):
        AccountGroupFactory(code="0", scheme=ChartScheme.MCH1, level=1)
        excel_path = _write_classification_excel(tmp_path, [(0, None, None, None, "Administration générale")])

        _run_classification(excel_path)

        assert AccountGroup.objects.filter(scheme=ChartScheme.MCH1).count() == 1
        assert AccountGroup.objects.filter(scheme=ChartScheme.MCH2).count() == 1

    def test_corrects_known_source_typo(self, tmp_path):
        excel_path = _write_classification_excel(
            tmp_path,
            [
                (None, "53", None, None, "Vieillesse et survivants"),
                (None, None, "352", None, "Prestations complémentaires AVS"),
                (None, None, None, "5320", "Prestations complémentaires AVS"),
            ],
        )

        _run_classification(excel_path)

        n2 = AccountGroup.objects.get(scheme=ChartScheme.MCH2, level=2, code="53")
        n3 = AccountGroup.objects.get(scheme=ChartScheme.MCH2, level=3, code="532")
        assert n3.parent == n2
        assert not AccountGroup.objects.filter(scheme=ChartScheme.MCH2, level=3, code="352").exists()

    def test_official_reference_file_has_documented_shape(self):
        """
        Locks in the canton reference file's node counts (10/69/159/180, see
        docs/mch2-migration.md) so a future edition of the file surfaces here
        instead of silently producing a different hierarchy shape.
        """
        if not DEFAULT_EXCEL_PATH.exists():
            pytest.skip("Reference file not checked out")

        _run_classification(DEFAULT_EXCEL_PATH)

        counts = {
            level: AccountGroup.objects.filter(scheme=ChartScheme.MCH2, level=level).count() for level in (1, 2, 3, 4)
        }
        assert counts == {1: 10, 2: 69, 3: 159, 4: 180}
