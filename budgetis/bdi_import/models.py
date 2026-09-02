from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from budgetis.common.models import ChartScheme
from budgetis.common.models import TimeStampedModel


class AccountImportLog(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        STARTED = "started", _("Started")
        SUCCESS = "success", _("Success")
        FAILED = "failed", _("Failed")

    class ImportKind(models.TextChoices):
        BDI = "bdi", _("BDI export")
        EXCEL = "excel", _("Manual Excel")

    kind = models.CharField(
        max_length=10,
        choices=ImportKind.choices,
        default=ImportKind.BDI,
        verbose_name=_("Kind"),
    )
    year = models.PositiveIntegerField(verbose_name=_("Year"))
    is_budget = models.BooleanField(verbose_name=_("Is budget"))
    scheme = models.CharField(
        max_length=10,
        choices=ChartScheme.choices,
        default=ChartScheme.MCH1,
        verbose_name=_("Scheme"),
    )
    file = models.FileField(upload_to="imports/accounts/", verbose_name=_("Import file"))

    launched_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Launched by"),
    )

    dry_run = models.BooleanField(default=False, verbose_name=_("Dry run"))
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("Status"),
    )

    message = models.TextField(blank=True, verbose_name=_("Message"))

    source_year = models.ForeignKey(
        "finance.AvailableYear",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Source year"),
    )
    copy_responsibles = models.BooleanField(default=True, verbose_name=_("Copy responsibles"))
    copy_labels = models.BooleanField(default=True, verbose_name=_("Copy labels"))
    copy_visibility = models.BooleanField(default=True, verbose_name=_("Copy visibility"))
    copy_comments = models.BooleanField(default=True, verbose_name=_("Copy comments"))

    class Meta:
        verbose_name = _("Account import log")
        verbose_name_plural = _("Account import logs")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        kind = _("Budget") if self.is_budget else _("Actual")
        return f"{self.year} - {kind} import ({self.created_at:%Y-%m-%d %H:%M})"


class ColumnMapping(TimeStampedModel):
    class Field(models.TextChoices):
        CODE = "code", _("Account code")
        FUNCTION = "function", _("Function")
        NATURE = "nature", _("Nature")
        SUB_ACCOUNT = "sub_account", _("Sub account")
        LABEL = "label", _("Account label")
        CHARGES = "charges", _("Charges")
        REVENUES = "revenues", _("Revenues")
        TOTAL = "total", _("Total (signed)")
        RESPONSIBLE = "responsible", _("Responsible (trigram)")

    log = models.ForeignKey(
        "AccountImportLog",
        on_delete=models.CASCADE,
        related_name="column_mappings",
        verbose_name=_("Import log"),
    )
    field = models.CharField(
        max_length=20,
        choices=Field.choices,
        verbose_name=_("Mapped field"),
    )
    column_name = models.CharField(
        max_length=100,
        verbose_name=_("Excel column name"),
    )

    derived_from_total = models.BooleanField(
        default=False,
        verbose_name=_("Derived from total column"),
        help_text=_("Use positive/negative values from 'total' column to infer charges/revenues."),
    )

    class Meta:
        unique_together = ("log", "field")
        verbose_name = _("Column mapping")
        verbose_name_plural = _("Column mappings")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_field_display()} ← {self.column_name}"
