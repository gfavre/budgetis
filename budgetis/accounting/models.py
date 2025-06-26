from django.contrib.auth import get_user_model
from django.db import models

from budgetis.common.models import TimeStampedModel


class AccountGroup(TimeStampedModel):
    """
    Represents a group of accounts (e.g., PCO, ADA).
    Each group is typically under the responsibility of a specific municipal member.
    """

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=3, unique=True)
    label = models.CharField(max_length=100)

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
    municipal_name = models.CharField(max_length=100)
    responsible = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        related_name="account_groups",
        null=True,
    )

    class Meta:
        unique_together = ("group", "year")

    def __str__(self) -> str:
        return f"{self.year} - {self.group.code} - {self.municipal_name}"


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
    group = models.ForeignKey(AccountGroup, on_delete=models.CASCADE)
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

    class Meta:
        unique_together = ("year", "function", "nature", "sub_account", "is_budget")
        indexes = [
            models.Index(fields=["year", "function"]),
            models.Index(fields=["year", "nature"]),
            models.Index(fields=["function", "nature", "sub_account"]),
        ]

    @property
    def full_code(self) -> str:
        """
        Returns the full code as 'function.nature', zero-padded to 3 digits.
        """
        return f"{self.function}.{self.nature}{('.' + self.sub_account) if self.sub_account else ''}"

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

    def __str__(self) -> str:
        return f"Comment by {self.author or 'Unknown'} on {self.account}"
