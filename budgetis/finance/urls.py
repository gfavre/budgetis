from __future__ import annotations

from django.urls import path

from .views import SankeyDataView
from .views import SankeyView


app_name = "finance"

urlpatterns = [
    path("sankey/", SankeyView.as_view(), name="index"),
    path("data/", SankeyDataView.as_view(), name="data_buckets"),
]
