from contextlib import suppress

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from budgetis.common.models import ChartScheme
from budgetis.common.models import TimeStampedModel


FUNDING_REQUEST_GTE = 500
DEPRECIATION_GTE = 600
DEPRECIATION_LT = 700

# MCH2 function codes are the 4-digit canonical group code (N4) plus one
# commune-specific digit; the group a MCH2 account belongs to is looked up by
# that 4-digit prefix rather than by an exact code match (see Account.save()).
MCH2_GROUP_CODE_LENGTH = 4


class AccountGroup(TimeStampedModel):
    """
    Represents one node of the functional classification hierarchy (e.g. MetaGroup
    1/2/3, SuperGroup 41/42/43, AccountGroup 720/460 in MCH1; N1-N4 in MCH2), all
    unified into a single self-referential tree so both schemes render through the
    same recursive grouping/template code regardless of how many levels deep they
    go (3 for MCH1, 4 for MCH2). The deepest level of a given scheme is the one a
    municipal officer is responsible for (see GroupResponsibility) and the one
    Account.group points to.
    """

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=5, db_index=True)
    label = models.CharField(max_length=100)
    scheme = models.CharField(max_length=10, choices=ChartScheme.choices, default=ChartScheme.MCH1)
    level = models.PositiveSmallIntegerField()
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )

    class Meta:
        unique_together = ("scheme", "level", "code")
        ordering = ("scheme", "level", "code")
        verbose_name = _("Account Group")
        verbose_name_plural = _("Account Groups")

    def __str__(self) -> str:
        return f"{self.code} - {self.label}"


class GroupResponsibility(models.Model):
    """
    Binds an AccountGroup to a municipal name (string) for a specific year.
    """

    group = models.ForeignKey(
        "AccountGroup",
        on_delete=models.CASCADE,
        related_name="responsibilities",
    )
    year = models.PositiveIntegerField()
    responsible = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name="account_groups",
        null=True,
    )

    class Meta:
        unique_together = ("group", "year")
        ordering = ("group__code", "year")
        verbose_name = _("Responsible")
        verbose_name_plural = _("Responsibles")

    def __str__(self) -> str:
        return f"{self.year} - {self.group.code} - {self.responsible.trigram if self.responsible else 'Unknown'}"


class AccountCodeMapping(TimeStampedModel):
    """
    Crosswalk between one historical MCH1 account code and its MCH2 equivalent,
    sourced from the commune's own conversion table. Not 1:1: several MCH1 rows
    can converge on the same MCH2 target (merge), and a single MCH1 row can also
    appear under several different MCH2 targets (split) — see
    budgetis.accounting.scheme_transition for how this is resolved into a
    continuous history per account.
    """

    mch1_function = models.CharField(verbose_name=_("MCH1 function"))
    mch1_nature = models.CharField(verbose_name=_("MCH1 nature"))
    mch1_sub_account = models.CharField(verbose_name=_("MCH1 subaccount"), blank=True)
    mch2_function = models.CharField(verbose_name=_("MCH2 function"))
    mch2_nature = models.CharField(verbose_name=_("MCH2 nature"))
    mch2_sub_account = models.CharField(verbose_name=_("MCH2 subaccount"), blank=True)

    class Meta:
        unique_together = (
            "mch1_function",
            "mch1_nature",
            "mch1_sub_account",
            "mch2_function",
            "mch2_nature",
            "mch2_sub_account",
        )
        ordering = ("mch2_function", "mch2_nature", "mch2_sub_account")
        verbose_name = _("Account code mapping")
        verbose_name_plural = _("Account code mappings")

    @staticmethod
    def _code(function: str, nature: str, sub_account: str) -> str:
        return f"{function}.{nature}" + (f".{sub_account}" if sub_account else "")

    @property
    def mch1_code(self) -> str:
        return self._code(self.mch1_function, self.mch1_nature, self.mch1_sub_account)

    @property
    def mch2_code(self) -> str:
        return self._code(self.mch2_function, self.mch2_nature, self.mch2_sub_account)

    def __str__(self) -> str:
        return f"{self.mch1_code} -> {self.mch2_code}"


class Account(TimeStampedModel):
    """
    Represents a specific account based on its full code structure.
    """

    class ExpectedType(models.TextChoices):
        CHARGE = "charges", _("Charges only")
        REVENUE = "revenues", _("Revenues only")
        BOTH = "both", _("Both charges and revenues")

    id = models.BigAutoField(primary_key=True)

    year = models.PositiveIntegerField(verbose_name=_("Year"), db_index=True)
    function = models.CharField(verbose_name=_("Function"), db_index=True)
    nature = models.CharField(verbose_name=_("Nature"), db_index=True)
    sub_account = models.CharField(verbose_name=_("Subaccount"), blank=True)

    label = models.CharField(verbose_name=_("Label"), max_length=255)
    group = models.ForeignKey(
        AccountGroup, on_delete=models.SET_NULL, verbose_name=_("Group"), null=True, related_name="accounts"
    )
    scheme = models.CharField(
        verbose_name=_("Scheme"), max_length=10, choices=ChartScheme.choices, default=ChartScheme.MCH1
    )
    is_budget = models.BooleanField(
        default=False,
    )  # True = Budget, False = Actual account

    charges = models.DecimalField(verbose_name=_("Charges"), max_digits=15, decimal_places=2)
    revenues = models.DecimalField(verbose_name=_("Revenues"), max_digits=15, decimal_places=2)
    expected_type = models.CharField(
        verbose_name=_("Expected type"),
        max_length=10,
        choices=ExpectedType.choices,
        default=ExpectedType.CHARGE,
    )
    visible_in_report = models.BooleanField(verbose_name=_("Visible in report"), default=True)

    class Meta:
        unique_together = ("year", "function", "nature", "sub_account", "is_budget")
        indexes = [
            models.Index(fields=["year", "function"]),
            models.Index(fields=["year", "nature"]),
            models.Index(fields=["function", "nature", "sub_account"]),
        ]
        ordering = ("function", "nature", "sub_account", "year")
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")

    @property
    def full_code(self) -> str:
        """
        Returns the full code as 'function.nature', zero-padded to 3 digits.
        """
        return f"{self.function}.{self.nature}{('.' + str(self.sub_account)) if self.sub_account else ''}"

    @property
    def is_funding_request(self) -> bool:
        """
        Funding request: Préavis municipal
        :return: Boolean indicating if the account is a funding request.
        """
        return FUNDING_REQUEST_GTE <= self.nature < DEPRECIATION_GTE

    @property
    def is_depreciation(self) -> bool:
        """
        Depreciation: Amortissement
        :return: Boolean indicating if the account is a depreciation account.
        """
        return DEPRECIATION_GTE <= self.nature < DEPRECIATION_LT

    @property
    def absolute_value(self):
        if self.charges:
            return abs(self.charges)
        return abs(self.revenues)

    def save(self, *args, **kwargs):
        if self.group is None:
            with suppress(AccountGroup.DoesNotExist):
                if self.scheme == ChartScheme.MCH2:
                    # MCH2 function = 4-digit group code (N4) + 1 commune digit.
                    group_code = self.function[:MCH2_GROUP_CODE_LENGTH]
                else:
                    # MCH1 function code matches its group code exactly.
                    group_code = self.function
                self.group = AccountGroup.objects.get(code=group_code, scheme=self.scheme)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        suffix = " (Budget)" if self.is_budget else ""
        return f"{self.year} - {self.full_code} - {self.label}{suffix}"


class AccountComment(models.Model):
    """
    Stores comments related to a specific account, typically used for explanations or reporting.
    """

    id = models.BigAutoField(primary_key=True)
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    content = models.TextField(verbose_name=_("Content"))

    class Meta:
        ordering = ("account__year", "account__nature", "account__function", "created_at")
        verbose_name = _("Account Comment")
        verbose_name_plural = _("Account Comments")

    def __str__(self) -> str:
        return f"Comment by {self.author or 'Unknown'} on {self.account}"
