from __future__ import annotations

from django.urls import path

from .views import SankeyDataView
from .views import SankeyMaticExportView
from .views import SankeyView


app_name = "finance"

urlpatterns = [
    path("sankey/", SankeyView.as_view(), name="index"),
    path("data/", SankeyDataView.as_view(), name="data_buckets"),
    path("sankeymatic/", SankeyMaticExportView.as_view(), name="sankeymatic_export"),
]
