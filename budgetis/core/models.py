from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _


class SiteConfiguration(models.Model):
    logo = models.ImageField(_("Logo"), upload_to="logos/", blank=True, null=True)
    commune_name = models.CharField(_("Commune name"), max_length=255, blank=True)
    gradient_start = models.CharField(
        _("Gradient start color"),
        max_length=7,
        default="#2f6ee2",  # bleu
        help_text=_("Couleur hexadécimale pour le haut du dégradé (ex. #2f6ee2)."),
    )
    gradient_end = models.CharField(
        _("Gradient end color"),
        max_length=7,
        default="#4caf50",  # vert
        help_text=_("Couleur hexadécimale pour le bas du dégradé (ex. #4caf50)."),
    )

    class Meta:
        verbose_name = _("Site configuration")
        verbose_name_plural = _("Site configuration")

    def __str__(self):
        return self.commune_name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete("site_configuration")  # purge cache

    @classmethod
    def get_cached(cls):
        config = cache.get("site_configuration")
        if config is None:
            config, _ = cls.objects.get_or_create(pk=1)
            cache.set("site_configuration", config, timeout=None)
        return config
