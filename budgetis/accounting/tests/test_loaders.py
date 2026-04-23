from decimal import Decimal

import pytest

from budgetis.accounting.loaders import ActualsLoader
from budgetis.accounting.loaders import BudgetLoader
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db


def _user():
    return UserFactory()


class TestActualsLoader:
    def test_load_returns_one_row_per_actual_account(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=False)
        rows = ActualsLoader().load(2024, _user(), only_responsible=False)
        assert len(rows) == 1

    def test_col1_is_actual_charges(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=False, charges=Decimal("1000"))
        rows = ActualsLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].col1_charges == Decimal("1000")

    def test_col2_is_budget_charges_when_budget_exists(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=False, charges=Decimal("1000"))
        AccountFactory(year=2024, function="720", nature="351", is_budget=True, charges=Decimal("800"))
        rows = ActualsLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].col2_charges == Decimal("800")

    def test_col2_is_zero_when_no_budget(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=False)
        rows = ActualsLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].col2_charges == Decimal("0.00")

    def test_col3_is_prev_actual_charges(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=False)
        AccountFactory(year=2023, function="720", nature="351", is_budget=False, charges=Decimal("900"))
        rows = ActualsLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].col3_charges == Decimal("900")

    def test_col3_is_zero_when_no_prev_actual(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=False)
        rows = ActualsLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].col3_charges == Decimal("0.00")

    def test_prev_actual_id_set_when_prev_account_exists(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=False)
        prev = AccountFactory(year=2023, function="720", nature="351", is_budget=False)
        rows = ActualsLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].account.prev_actual_id == prev.id

    def test_prev_actual_id_is_none_when_no_prev_account(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=False)
        rows = ActualsLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].account.prev_actual_id is None

    def test_prev_actual_comment_count_is_zero_when_no_prev(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=False)
        rows = ActualsLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].account.prev_actual_comment_count == 0

    def test_budget_fallback_when_no_actuals_exist(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=True, charges=Decimal("500"))
        rows = ActualsLoader().load(2024, _user(), only_responsible=False)
        assert len(rows) == 1
        assert rows[0].col2_charges == Decimal("500")

    def test_invisible_accounts_excluded(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=False, visible_in_report=False)
        rows = ActualsLoader().load(2024, _user(), only_responsible=False)
        assert rows == []


class TestBudgetLoader:
    def test_load_returns_one_row_per_budget_account(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=True)
        rows = BudgetLoader().load(2024, _user(), only_responsible=False)
        assert len(rows) == 1

    def test_col1_is_budget_charges(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=True, charges=Decimal("1200"))
        rows = BudgetLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].col1_charges == Decimal("1200")

    def test_col2_is_prev_budget_charges_when_exists(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=True)
        AccountFactory(year=2023, function="720", nature="351", is_budget=True, charges=Decimal("950"))
        rows = BudgetLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].col2_charges == Decimal("950")

    def test_col2_is_zero_when_no_prev_budget(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=True)
        rows = BudgetLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].col2_charges == Decimal("0.00")

    def test_col3_is_actuals_n_minus_2(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=True)
        AccountFactory(year=2022, function="720", nature="351", is_budget=False, charges=Decimal("870"))
        rows = BudgetLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].col3_charges == Decimal("870")

    def test_col3_is_zero_when_no_actuals(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=True)
        rows = BudgetLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].col3_charges == Decimal("0.00")

    def test_actuals_id_set_when_actuals_exist(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=True)
        actuals = AccountFactory(year=2022, function="720", nature="351", is_budget=False)
        rows = BudgetLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].account.actuals_id == actuals.id

    def test_actuals_id_is_none_when_no_actuals(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=True)
        rows = BudgetLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].account.actuals_id is None

    def test_actuals_comment_count_is_zero_when_no_actuals(self):
        AccountFactory(year=2024, function="720", nature="351", is_budget=True)
        rows = BudgetLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].account.actuals_comment_count == 0

    def test_budget_id_is_account_id(self):
        acc = AccountFactory(year=2024, function="720", nature="351", is_budget=True)
        rows = BudgetLoader().load(2024, _user(), only_responsible=False)
        assert rows[0].account.budget_id == acc.id
