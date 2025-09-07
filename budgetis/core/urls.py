from django.urls import path

from .views import favicon_view
from .views import home_view


urlpatterns = [
    path("", home_view, name="home"),
    path("favicon-<int:size>.png", favicon_view, name="favicon"),
]
