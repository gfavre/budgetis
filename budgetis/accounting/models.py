from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from budgetis.common.models import TimeStampedModel


FUNDING_REQUEST_GTE = 500
DEPRECIATION_GTE = 600
DEPRECIATION_LT = 700


class MetaGroup(TimeStampedModel):
    """
    Represents a meta group of accounts (e.g. 1, 2, 3).
    """

    id = models.BigAutoField(primary_key=True)
    code = models.SmallIntegerField(db_index=True, unique=True)
    label = models.CharField(max_length=100)

    class Meta:
        ordering = ("code",)
        verbose_name = _("Meta Group")
        verbose_name_plural = _("Meta Groups")

    def __str__(self) -> str:
        return f"{self.code} - {self.label}"


class SuperGroup(TimeStampedModel):
    """
    Represents a super group of accounts (e.g. 41, 42, 43).
    """

    id = models.BigAutoField(primary_key=True)
    code = models.SmallIntegerField(db_index=True, unique=True)
    label = models.CharField(max_length=100)
    metagroup = models.ForeignKey(MetaGroup, on_delete=models.SET_NULL, null=True, related_name="supergroups")

    class Meta:
        ordering = ("code",)
        verbose_name = _("Super Group")
        verbose_name_plural = _("Super Groups")

    def __str__(self) -> str:
        return f"{self.code} - {self.label}"


class AccountGroup(TimeStampedModel):
    """
    Represents a group of accounts (e.g., PCO, ADA).
    Each group is typically under the responsibility of a specific municipal member.
    """

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=5, db_index=True, unique=True)
    label = models.CharField(max_length=100)
    supergroup = models.ForeignKey(SuperGroup, on_delete=models.SET_NULL, null=True, related_name="groups")

    class Meta:
        ordering = ("code",)
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


class Account(TimeStampedModel):
    """
    Represents a specific account based on its full code structure.
    """

    EXPECTED_TYPES = [
        ("charges", "Charges only"),
        ("revenues", "Revenues only"),
        ("both", "Both charges and revenues"),
    ]
    id = models.BigAutoField(primary_key=True)

    year = models.PositiveIntegerField(db_index=True)
    function = models.SmallIntegerField(db_index=True)
    nature = models.SmallIntegerField(db_index=True)
    sub_account = models.SmallIntegerField(null=True, blank=True)

    label = models.CharField(max_length=255)
    group = models.ForeignKey(AccountGroup, on_delete=models.SET_NULL, null=True, related_name="accounts")
    is_budget = models.BooleanField(
        default=False,
    )  # True = Budget, False = Actual account

    charges = models.DecimalField(max_digits=15, decimal_places=2)
    revenues = models.DecimalField(max_digits=15, decimal_places=2)
    expected_type = models.CharField(
        max_length=10,
        choices=EXPECTED_TYPES,
        default="charges",
    )
    # visible_in_report = models.BooleanField(default=True)

    class Meta:
        unique_together = ("year", "function", "nature", "sub_account", "is_budget")
        indexes = [
            models.Index(fields=["year", "function"]),
            models.Index(fields=["year", "nature"]),
            models.Index(fields=["function", "nature", "sub_account"]),
        ]
        ordering = ("year", "nature", "function", "nature", "sub_account")
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
    content = models.TextField()

    class Meta:
        ordering = ("account__year", "account__nature", "account__function", "created_at")
        verbose_name = _("Account Comment")
        verbose_name_plural = _("Account Comments")

    def __str__(self) -> str:
        return f"Comment by {self.author or 'Unknown'} on {self.account}"
