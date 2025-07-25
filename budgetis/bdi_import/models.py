from django.contrib.auth import get_user_model
from django.db import models

from budgetis.common.models import TimeStampedModel


class AccountImportLog(TimeStampedModel):
    """
    Logs each CSV/XLSX account import (budget or actual) for traceability.
    """

    year = models.PositiveIntegerField()
    is_budget = models.BooleanField()
    file_path = models.TextField()
    launched_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    dry_run = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("started", "Started"),
            ("success", "Success"),
            ("failed", "Failed"),
        ],
        default="pending",
    )
    message = models.TextField(blank=True)

    def __str__(self) -> str:
        kind = "Budget" if self.is_budget else "Comptes"
        return f"{self.year} - {kind} import ({self.created_at:%Y-%m-%d %H:%M})"
