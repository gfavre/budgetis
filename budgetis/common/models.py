from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class ChartScheme(models.TextChoices):
    """
    Municipal chart-of-accounts numbering scheme. Genolier uses MCH1 through the
    2026 budget/actuals, MCH2 from the 2027 budget onward; both stay permanently
    queryable side by side.
    """

    MCH1 = "mch1", _("MCH1")
    MCH2 = "mch2", _("MCH2")
