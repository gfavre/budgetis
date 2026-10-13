from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction
from django.template.loader import render_to_string

from budgetis.accounting.groupers import build_grouped
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.accounting.tests.factories import AccountGroupFactory
from budgetis.accounting.tests.factories import FunctionCategoryFactory
from budgetis.accounting.tests.factories import FunctionSplitFactory
from budgetis.accounting.tests.factories import GroupResponsibilityFactory
from budgetis.accounting.views.data import AccountRow
from budgetis.common.models import ChartScheme


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(("scheme", "level", "code"), [(ChartScheme.MCH1, 4, "9630"), (ChartScheme.MCH2, 3, "963")])
def test_split_rejects_non_n4_groups(scheme, level, code):
    split = FunctionSplitFactory(group=AccountGroupFactory(scheme=scheme, level=level, code=code))
    with pytest.raises(ValidationError) as error:
        split.full_clean()
    assert "group" in error.value.message_dict


@pytest.mark.parametrize("function", ["02901", "9630", "963011", "9630a", "9630\u0661"])
def test_category_rejects_invalid_function(function):
    category = FunctionCategoryFactory.build(split=FunctionSplitFactory(), function=function)
    with pytest.raises(ValidationError):
        category.full_clean()


def test_category_unique_per_split():
    category = FunctionCategoryFactory()
    category.full_clean()
    category.split.full_clean()
    with transaction.atomic(), pytest.raises(IntegrityError):
        FunctionCategoryFactory(split=category.split)


@pytest.mark.parametrize("enabled", [True, False])
def test_split_preserves_totals_rows_and_responsibles(enabled):
    root = AccountGroupFactory(scheme=ChartScheme.MCH2, level=1, code="9")
    group = AccountGroupFactory(scheme=ChartScheme.MCH2, level=4, code="9630", parent=root)
    split = FunctionSplitFactory(group=group, enabled=enabled)
    FunctionCategoryFactory(split=split)
    FunctionCategoryFactory(split=split, function="96309", label="Unused building")
    accounts = [
        AccountFactory(group=group, scheme=ChartScheme.MCH2, function=function, year=2026)
        for function in ("96302", "96301")
    ]
    rows = [
        AccountRow(account=account, col1_charges=Decimal("10"), col2_revenues=Decimal("20")) for account in accounts
    ]
    default = GroupResponsibilityFactory(group=group, year=2026)
    override = GroupResponsibilityFactory(group=group, year=2026, function="96301")
    tree = build_grouped(rows, 2026)
    node = tree["9"]["children"]["9630"]
    assert node["col1_charges"] == tree["9"]["col1_charges"] == Decimal("20")
    assert node["col2_revenues"] == Decimal("40")
    if not enabled:
        assert not node["children"]
        assert node["accounts"] == list(reversed(rows))
        return
    assert list(node["children"]) == ["96301", "96302"]
    assert not node["accounts"]
    assert node["children"]["96301"]["label"] == "Maison gothique"
    assert node["children"]["96302"]["label"] == ""
    assert node["children"]["96301"]["responsible"] == override.responsible
    assert node["children"]["96302"]["responsible"] == default.responsible
    assert node["children"]["96301"]["accounts"] == [rows[1]]
    for template in ("group_node.html", "budget_group_node.html"):
        html = render_to_string(
            f"accounting/partials/{template}",
            {"node": node, "year": 2026, "show_col2": True, "show_col3": False},
        )
        assert 'id="group-96301"' in html
        assert 'id="group-96302"' in html
        assert "Maison gothique" in html
        assert html.count(accounts[0].full_code) == 1
        assert html.count(accounts[1].full_code) == 1
        assert 'id="comments-group-96301"' in html
        assert 'href="#group-96302"' in html
        assert "Unused building" not in html
