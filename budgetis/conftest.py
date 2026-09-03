import base64

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile

from budgetis.core.models import SiteConfiguration
from budgetis.users.models import User
from budgetis.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def _media_storage(settings, tmpdir) -> None:
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user(db) -> User:
    return UserFactory()


# A minimal 1x1 PNG - base.html always renders {{ config.logo.url }}, which
# raises if SiteConfiguration has no logo file attached.
_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture
def site_configuration_with_logo(db) -> SiteConfiguration:
    """
    Only needed by tests that render a full page (base.html) rather than
    calling a view directly - use it whenever a test hits `client.get(...)`
    on a page other tests haven't already exercised end to end.

    SiteConfiguration.get_cached() caches the singleton row for the life of
    the process, so a stale cached instance from an earlier test (created
    without a logo) would otherwise survive into this one - update_or_create
    plus re-priming the cache keeps this fixture correct regardless of test
    order.
    """
    cache.delete("site_configuration")
    config, _ = SiteConfiguration.objects.update_or_create(
        pk=1, defaults={"logo": SimpleUploadedFile("logo.png", _ONE_PIXEL_PNG, content_type="image/png")}
    )
    cache.set("site_configuration", config, timeout=None)
    return config
