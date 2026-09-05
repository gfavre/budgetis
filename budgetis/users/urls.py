from django.urls import path

from .views import user_admin_edit_view
from .views import user_detail_view
from .views import user_management_view
from .views import user_redirect_view
from .views import user_update_view


app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("management/", view=user_management_view, name="management"),
    path("<int:pk>/edit/", view=user_admin_edit_view, name="admin-edit"),
    path("<int:pk>/", view=user_detail_view, name="detail"),
]
