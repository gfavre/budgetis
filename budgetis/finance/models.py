from django.db import models
from django.utils.translation import gettext_lazy as _

from budgetis.common.models import ChartScheme
from budgetis.common.models import TimeStampedModel


class AvailableYear(models.Model):
    class YearType(models.TextChoices):
        BUDGET = "budget", _("Budget")
        ACTUAL = "actual", _("Comptes")

    year = models.PositiveSmallIntegerField(verbose_name=_("Year"))
    type = models.CharField(max_length=10, choices=YearType.choices, verbose_name=_("Type"))
    scheme = models.CharField(
        max_length=10, choices=ChartScheme.choices, default=ChartScheme.MCH1, verbose_name=_("Scheme")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Available year")
        verbose_name_plural = _("Available years")
        unique_together = ("year", "type")
        ordering = ("-year",)

    def __str__(self):
        return f"{self.year} ({self.get_type_display()})"


class SankeyFlow(models.TextChoices):
    """Which block of the Sankey diagram a category's node lives under."""

    REVENUE = "revenue", _("Revenue")
    CANTON = "canton", _("Canton")
    INTERCOMMUNALITY = "intercommunality", _("Intercommunality")
    COMMUNE = "commune", _("Commune")
    DOTATION = "dotation", _("Dotation")


class SankeyCategory(TimeStampedModel):
    """
    One labeled bucket in the Sankey diagram (e.g. "Salaires", "AISGE",
    "Péréquation"). Scheme-agnostic - the same bucket identity is shared by
    both MCH1 and MCH2, only the rules matching accounts into it differ.
    """

    name = models.CharField(max_length=100, unique=True)
    flow = models.CharField(max_length=20, choices=SankeyFlow)
    color = models.CharField(max_length=7)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("flow", "order")
        verbose_name = _("Sankey category")
        verbose_name_plural = _("Sankey categories")

    def __str__(self) -> str:
        return self.name


class SankeyNatureRangeRule(TimeStampedModel):
    """
    Assigns every account whose nature falls in [nature_start, nature_end] to
    a category, for a given scheme. Rules are checked in ascending `priority`
    order, first match wins - a narrow, low-priority range (e.g. a single
    nature) can carve an exception out of a broader, higher-priority one.
    """

    scheme = models.CharField(max_length=10, choices=ChartScheme.choices)
    nature_start = models.PositiveIntegerField(verbose_name=_("From nature"))
    nature_end = models.PositiveIntegerField(verbose_name=_("To nature"))
    priority = models.PositiveSmallIntegerField(default=100)
    category = models.ForeignKey(SankeyCategory, on_delete=models.CASCADE, related_name="nature_range_rules")

    class Meta:
        ordering = ("scheme", "priority", "nature_start")
        verbose_name = _("Sankey nature range rule")
        verbose_name_plural = _("Sankey nature range rules")

    def __str__(self) -> str:
        return f"{self.scheme} {self.nature_start}-{self.nature_end} → {self.category}"

    def matches(self, nature: int) -> bool:
        return self.nature_start <= nature <= self.nature_end


class SankeyAccountCodeRule(TimeStampedModel):
    """
    Assigns one exact function.nature[.sub_account] code to a category, for a
    given scheme. Takes priority over nature-range rules - for the handful of
    accounts (canton péréquation, police, social security...) identifiable by
    a single stable code rather than a whole nature family.
    """

    scheme = models.CharField(max_length=10, choices=ChartScheme.choices)
    function = models.CharField(max_length=10, verbose_name=_("Function"))
    nature = models.CharField(max_length=10, verbose_name=_("Nature"))
    sub_account = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_("Subaccount"),
        help_text=_("Leave blank to match any subaccount under this function/nature."),
    )
    category = models.ForeignKey(SankeyCategory, on_delete=models.CASCADE, related_name="account_code_rules")

    class Meta:
        unique_together = ("scheme", "function", "nature", "sub_account")
        ordering = ("scheme", "function", "nature")
        verbose_name = _("Sankey account code rule")
        verbose_name_plural = _("Sankey account code rules")

    def __str__(self) -> str:
        code = f"{self.function}.{self.nature}"
        if self.sub_account:
            code += f".{self.sub_account}"
        return f"{self.scheme} {code} → {self.category}"


class SankeyLabelRule(TimeStampedModel):
    """
    Assigns every account whose label contains `pattern` (case-insensitive)
    to a category, for a given scheme. For entities (AISGE, APEC, SDIS...)
    scattered across unrelated function codes with no shared nature/code
    pattern, only identifiable by the words in their label.
    """

    scheme = models.CharField(max_length=10, choices=ChartScheme.choices)
    pattern = models.CharField(
        max_length=100, verbose_name=_("Label contains"), help_text=_("Case-insensitive substring match.")
    )
    category = models.ForeignKey(SankeyCategory, on_delete=models.CASCADE, related_name="label_rules")

    class Meta:
        ordering = ("scheme", "pattern")
        verbose_name = _("Sankey label rule")
        verbose_name_plural = _("Sankey label rules")

    def __str__(self) -> str:
        return f"{self.scheme} '{self.pattern}' → {self.category}"
