from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal

from budgetis.accounting.models import Account


@dataclass
class AccountRow:
    """
    Normalised data container for one account across three comparison columns.

    col1 = primary column   (actuals N  for comptes, budget N   for budget)
    col2 = secondary column (budget N   for comptes, budget N-1 for budget)
    col3 = historical column(actuals N-1 for comptes, actuals N-2 for budget)

    The account object carries non-financial display data (label, full_code,
    comment_count, budget_id, budget_comment_count) attached by the loader.
    """

    account: Account
    col1_charges: Decimal = field(default_factory=Decimal)
    col1_revenues: Decimal = field(default_factory=Decimal)
    col2_charges: Decimal = field(default_factory=Decimal)
    col2_revenues: Decimal = field(default_factory=Decimal)
    col3_charges: Decimal = field(default_factory=Decimal)
    col3_revenues: Decimal = field(default_factory=Decimal)
