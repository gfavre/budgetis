from dataclasses import dataclass

from django.db import models
from django.utils.translation import gettext_lazy as _

from budgetis.accounting.models import AccountCodeMapping
from budgetis.common.models import ChartScheme
from budgetis.finance.models import AvailableYear


AccountCode = tuple[str, str, str]


class MappingKind(models.TextChoices):
    ONE_TO_ONE = "one_to_one", _("One to one")
    MERGE = "merge", _("Merge")
    SPLIT = "split", _("Split")
    NEW = "new", _("New")


@dataclass(frozen=True)
class AccountOrigin:
    kind: MappingKind
    mch1_codes: list[AccountCode]


def classify_mch2_account(function: str, nature: str, sub_account: str) -> AccountOrigin:
    """
    Resolve how an MCH2 account relates to its MCH1 history via AccountCodeMapping:
    no mapping row at all -> NEW; any contributing MCH1 origin that also maps to a
    *different* MCH2 target -> SPLIT (this covers the merge+split hybrid, which is
    treated as a split); several origins, none splitting elsewhere -> MERGE;
    exactly one, non-splitting origin -> ONE_TO_ONE.
    """
    mappings = AccountCodeMapping.objects.filter(
        mch2_function=function, mch2_nature=nature, mch2_sub_account=sub_account
    )
    origins: set[AccountCode] = {(m.mch1_function, m.mch1_nature, m.mch1_sub_account) for m in mappings}

    if not origins:
        return AccountOrigin(kind=MappingKind.NEW, mch1_codes=[])

    for origin_function, origin_nature, origin_sub_account in origins:
        splits_elsewhere = (
            AccountCodeMapping.objects.filter(
                mch1_function=origin_function,
                mch1_nature=origin_nature,
                mch1_sub_account=origin_sub_account,
            )
            .exclude(mch2_function=function, mch2_nature=nature, mch2_sub_account=sub_account)
            .exists()
        )
        if splits_elsewhere:
            return AccountOrigin(kind=MappingKind.SPLIT, mch1_codes=sorted(origins))

    kind = MappingKind.MERGE if len(origins) > 1 else MappingKind.ONE_TO_ONE
    return AccountOrigin(kind=kind, mch1_codes=sorted(origins))


def first_mch2_year(year_type: str) -> int | None:
    """The first year AvailableYear records as already using MCH2, for the given YearType."""
    available_year = AvailableYear.objects.filter(type=year_type, scheme=ChartScheme.MCH2).order_by("year").first()
    return available_year.year if available_year else None
