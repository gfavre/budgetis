from django.db import models
from django.utils.translation import gettext_lazy as _


class AvailableYear(models.Model):
    class YearType(models.TextChoices):
        BUDGET = "budget", _("Budget")
        ACTUAL = "actual", _("Comptes")

    year = models.PositiveSmallIntegerField(verbose_name=_("Year"))
    type = models.CharField(max_length=10, choices=YearType.choices, verbose_name=_("Type"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Available year")
        verbose_name_plural = _("Available years")
        unique_together = ("year", "type")
        ordering = ("-year",)

    def __str__(self):
        return f"{self.year} ({self.get_type_display()})"
