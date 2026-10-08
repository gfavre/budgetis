"""
Wording that differs between MCH1 and MCH2 (e.g. "Compte de fonctionnement"
became "Compte de résultats"). The wording follows the chart scheme of the
year being displayed, so MCH1 years keep the terms they were adopted with.
"""

from django import template
from django.utils.translation import gettext_lazy as _

from budgetis.accounting.scheme_transition import year_scheme
from budgetis.common.models import ChartScheme


register = template.Library()

OPERATING_ACCOUNT = "operating_account"
ACCOUNTS_BY_FUNCTION = "accounts_by_function"

TERMS = {
    OPERATING_ACCOUNT: {
        ChartScheme.MCH1: _("Operating account"),
        ChartScheme.MCH2: _("Income statement"),
    },
    ACCOUNTS_BY_FUNCTION: {
        ChartScheme.MCH1: _("Accounts by administrative function"),
        ChartScheme.MCH2: _("Accounts by functional classification"),
    },
}


@register.simple_tag
def chart_term(term: str, year: int | None) -> str:
    """The wording of `term` for the chart scheme `year` was recorded under (MCH1 if unknown)."""
    scheme = (year and year_scheme(year)) or ChartScheme.MCH1
    return TERMS[term][scheme]
