# ruff: noqa: PLR2004
from http import HTTPStatus

import pytest
from django.urls import reverse

from budgetis.accounting.migration_report import build_migration_report
from budgetis.accounting.models import AccountCodeMapping
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.common.models import ChartScheme
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def mapping(source, target):
    AccountCodeMapping.objects.create(
        mch1_function=source,
        mch1_nature="300",
        mch2_function=target,
        mch2_nature="3000",
        mch2_sub_account="00",
    )


def test_split_merge_overlap_and_distinct_accounts():
    mapping("100", "01100")  # simple
    mapping("200", "02100")  # split only
    mapping("200", "02200")
    mapping("300", "03100")  # merge only
    mapping("400", "03100")  # complex
    mapping("400", "04100")
    for year in [2024, 2025]:
        AccountFactory(function="900", nature="300", sub_account="", year=year, scheme=ChartScheme.MCH1)
    report = build_migration_report()
    assert report["total"] == 5
    assert report["mapped"] == 4
    assert report["unmapped"] == 1
    assert report["split"] == 2
    assert report["merged"] == 2
    assert report["complex"] == 1
    assert report["merged_targets"] == 1
    assert report["simple"] == 1
    assert report["recomposed"] == 3
    assert report["simple_percent"] == 25
    assert report["recomposed_percent"] == 75
    merged_row = next(row for row in report["reverse_rows"] if row["code"] == "03100.3000.00")
    assert [link["code"] for link in merged_row["links"]] == ["300.300", "400.300"]


def test_empty_report():
    report = build_migration_report()
    assert report["mapped"] == report["simple_percent"] == report["recomposed_percent"] == 0
    assert report["example"] is None
    assert report["forward_rows"] == report["reverse_rows"] == []


def test_unmapped_target_and_latest_label():
    for year, label in [(2024, "Ancien libellé"), (2025, "Nouveau libellé")]:
        AccountFactory(
            function="01100",
            nature="3000",
            sub_account="00",
            year=year,
            label=label,
            scheme=ChartScheme.MCH2,
        )
    report = build_migration_report()
    assert report["reverse_rows"][0]["label"] == "Nouveau libellé"
    assert report["reverse_rows"][0]["links"] == []


def test_report_requires_login(client):
    response = client.get(reverse("accounting:mch2-migration-report"))
    assert response.status_code == HTTPStatus.FOUND


def test_report_renders_both_directions(client, site_configuration_with_logo):
    mapping("100", "01100")
    client.force_login(UserFactory())
    response = client.get(reverse("accounting:mch2-migration-report"))
    assert response.status_code == HTTPStatus.OK
    content = response.content.decode()
    assert "100.300" in content
    assert "01100.3000.00" in content
    assert "Destination des comptes" in content
    assert "Provenance des comptes" in content
    assert "window.print()" in content
