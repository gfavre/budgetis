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
    for source in ["100", "200", "300", "400"]:
        AccountFactory(
            function=source, nature="300", sub_account="", year=2025, scheme=ChartScheme.MCH1, is_budget=True
        )
    for year in [2024, 2025]:
        AccountFactory(
            function="900", nature="300", sub_account="", year=year, scheme=ChartScheme.MCH1, is_budget=True
        )
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
    assert report["reading_example_label"] == ""
    assert report["forward_rows"] == report["reverse_rows"] == []
    assert report["split_example"] == report["merge_example"] == []


def test_examples_are_selected_from_current_mapping():
    for source, target in [("100", "01100"), ("100", "01200"), ("200", "01200")]:
        mapping(source, target)
    report = build_migration_report()
    assert report["split_example"][0]["code"] == "100.300"
    assert [link["code"] for link in report["split_example"][0]["links"]] == [
        "01100.3000.00",
        "01200.3000.00",
    ]
    assert report["merge_example"][0]["code"] == "01200.3000.00"
    assert [link["code"] for link in report["merge_example"][0]["links"]] == ["100.300", "200.300"]


def test_reading_example_uses_latest_exact_mch2_account_label():
    for year, label in [(2024, "Ancien libellé"), (2025, "Entretien des routes - déneigement")]:
        AccountFactory(
            scheme=ChartScheme.MCH2,
            function="61500",
            nature="3141",
            sub_account="01",
            year=year,
            label=label,
        )
    AccountFactory(
        scheme=ChartScheme.MCH2,
        function="61500",
        nature="3141",
        sub_account="02",
        year=2026,
        label="Autre subdivision",
    )
    assert build_migration_report()["reading_example_label"] == "Entretien des routes - déneigement"


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


def test_balance_and_investments_excluded_from_report():
    AccountFactory(scheme=ChartScheme.MCH1, function="3500", nature="301", sub_account="", is_budget=True)
    AccountFactory(scheme=ChartScheme.MCH1, function="170", nature="300", sub_account="", is_budget=True)
    for function, nature in [("9100", "1"), ("9100", "300"), ("170", "503"), ("170", "661")]:
        AccountFactory(scheme=ChartScheme.MCH1, function=function, nature=nature, sub_account="")
    for nature in ["1000", "2000", "5010", "6010"]:
        AccountFactory(scheme=ChartScheme.MCH2, function="61500", nature=nature, sub_account="")
    mapping("170", "61500")
    AccountCodeMapping.objects.create(
        mch1_function="170",
        mch1_nature="503",
        mch2_function="61500",
        mch2_nature="5010",
    )
    report = build_migration_report()
    assert {row["code"] for row in report["forward_rows"]} == {"3500.301", "170.300"}
    assert {row["code"] for row in report["reverse_rows"]} == {"61500.3000.00"}
    assert report["total"] == 2
    assert report["unmapped"] == 1


def test_only_latest_mch1_budget_sources_are_compared():
    AccountFactory(scheme=ChartScheme.MCH1, function="100", nature="300", sub_account="", year=2025, is_budget=True)
    AccountFactory(scheme=ChartScheme.MCH1, function="200", nature="300", sub_account="", year=2026, is_budget=True)
    AccountFactory(scheme=ChartScheme.MCH1, function="300", nature="300", sub_account="", year=2027, is_budget=False)
    AccountFactory(scheme=ChartScheme.MCH2, function="01100", nature="3000", year=2028, is_budget=True)
    mapping("100", "01100")
    mapping("200", "01100")
    report = build_migration_report()
    assert report["reference_year"] == 2026
    assert report["total"] == report["mapped"] == report["simple"] == 1
    assert report["unmapped"] == report["merged"] == 0
    assert [row["code"] for row in report["forward_rows"]] == ["200.300"]
    target = next(row for row in report["reverse_rows"] if row["code"] == "01100.3000.00")
    assert [link["code"] for link in target["links"]] == ["200.300"]


def test_zero_notes_use_latest_budget_and_actuals_and_never_net_amounts():
    for function in ["100", "200", "300"]:
        AccountFactory(
            scheme=ChartScheme.MCH1,
            function=function,
            nature="300",
            sub_account="",
            year=2026,
            is_budget=True,
            charges=0,
            revenues=0,
        )
    AccountFactory(
        scheme=ChartScheme.MCH1,
        function="100",
        nature="300",
        sub_account="",
        year=2025,
        is_budget=False,
        charges=0,
        revenues=0,
    )
    AccountFactory(
        scheme=ChartScheme.MCH1,
        function="200",
        nature="300",
        sub_account="",
        year=2025,
        is_budget=False,
        charges=100,
        revenues=100,
    )
    AccountFactory(
        scheme=ChartScheme.MCH1,
        function="300",
        nature="300",
        sub_account="",
        year=2024,
        is_budget=False,
        charges=0,
        revenues=0,
    )
    rows = {row["code"]: row for row in build_migration_report()["forward_rows"]}
    assert rows["100.300"]["zero_notes"] == ["Budget 2026: à zéro", "Comptes 2025: à zéro"]
    assert rows["200.300"]["zero_notes"] == ["Budget 2026: à zéro"]
    assert rows["300.300"]["zero_notes"] == ["Budget 2026: à zéro"]


def test_zero_notes_only_for_accounts_without_correspondence():
    for function in ["100", "200"]:
        AccountFactory(
            scheme=ChartScheme.MCH1,
            function=function,
            nature="300",
            sub_account="",
            year=2026,
            is_budget=True,
            charges=0,
            revenues=0,
        )
    AccountFactory(
        scheme=ChartScheme.MCH2,
        function="01100",
        nature="3000",
        sub_account="00",
        year=2027,
        is_budget=True,
        charges=0,
        revenues=0,
    )
    mapping("100", "01100")
    report = build_migration_report()
    rows = {row["code"]: row for row in report["forward_rows"]}
    assert rows["100.300"]["zero_notes"] == []
    assert rows["200.300"]["zero_notes"] == ["Budget 2026: à zéro"]
    assert report["reverse_rows"][0]["zero_notes"] == []
