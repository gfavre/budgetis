from __future__ import annotations

from django.urls import path

from .views import SankeyCategoryEditView
from .views import SankeyDataView
from .views import SankeyMaticExportView
from .views import SankeyRuleCreateView
from .views import SankeyRulesView
from .views import SankeyRuleUpdateView
from .views import SankeyView


app_name = "finance"

urlpatterns = [
    path("sankey/", SankeyView.as_view(), name="index"),
    path("sankey/rules/", SankeyRulesView.as_view(), name="sankey-rules"),
    path(
        "sankey/rules/category/<int:pk>/edit/",
        SankeyCategoryEditView.as_view(),
        name="sankey-category-edit",
    ),
    path(
        "sankey/rules/<str:rule_type>/add/<int:category_id>/",
        SankeyRuleCreateView.as_view(),
        name="sankey-rule-add",
    ),
    path(
        "sankey/rules/<str:rule_type>/<int:pk>/edit/",
        SankeyRuleUpdateView.as_view(),
        name="sankey-rule-edit",
    ),
    path("data/", SankeyDataView.as_view(), name="data_buckets"),
    path("sankeymatic/", SankeyMaticExportView.as_view(), name="sankeymatic_export"),
]
