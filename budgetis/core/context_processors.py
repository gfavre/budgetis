from budgetis import __version__

from .models import SiteConfiguration


def site_config(request):
    """Expose SiteConfiguration comme 'config' dans tous les templates."""
    return {"config": SiteConfiguration.get_cached()}


def app_version(request):
    """Expose the app version as 'app_version' in every template, including the admin."""
    return {"app_version": __version__}
