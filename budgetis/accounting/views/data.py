from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
from typing import TYPE_CHECKING

from budgetis.accounting.models import Account


if TYPE_CHECKING:
    from budgetis.users.models import User


@dataclass
class AccountRow:
    """
    Normalised data container for one account across three comparison columns.

    col1 = primary column   (actuals N  for comptes, budget N   for budget)
    col2 = secondary column (budget N   for comptes, budget N-1 for budget)
    col3 = historical column(actuals N-1 for comptes, actuals N-2 for budget)

    The account object carries non-financial display data (label, full_code,
    comment_count, budget_id, budget_comment_count) attached by the loader.

    `responsible` is set by groupers.build_grouped() - the account's own
    responsible, resolved against a per-function GroupResponsibility override
    if one exists for its exact function, else the group-level default.
    """

    account: Account
    col1_charges: Decimal = field(default_factory=Decimal)
    col1_revenues: Decimal = field(default_factory=Decimal)
    col2_charges: Decimal = field(default_factory=Decimal)
    col2_revenues: Decimal = field(default_factory=Decimal)
    col3_charges: Decimal = field(default_factory=Decimal)
    col3_revenues: Decimal = field(default_factory=Decimal)
    responsible: "User | None" = None
