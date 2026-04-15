import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def test_setup(settings):
    settings.SECURE_SSL_REDIRECT = False
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
    cache.clear()
