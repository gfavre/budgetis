from .models import SiteConfiguration


def site_config(request):
    """Expose SiteConfiguration comme 'config' dans tous les templates."""
    return {"config": SiteConfiguration.get_cached()}
