from pathlib import Path

from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import models
from django.utils.translation import gettext_lazy as _
from PIL import Image


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

    def generate_favicon(self, size: int) -> str | None:
        """
        Generate a favicon of the given size from the logo.

        Args:
            size (int): Target size (width and height in px).

        Returns:
            str | None: Path to the generated favicon relative to MEDIA_ROOT,
                        or None if no logo is set.
        """
        if not self.logo:
            return None

        input_path = self.logo.path
        output_dir = Path("favicons")
        output_dir_full = Path(default_storage.location) / output_dir
        output_dir_full.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"favicon-{size}x{size}.png"
        output_path = output_dir_full / output_file.name

        if not output_path.exists():
            with Image.open(input_path) as img:
                converted = img.convert("RGBA")
                resized = converted.resize((size, size), Image.LANCZOS)
                resized.save(output_path, format="PNG")

        return str(output_file)
