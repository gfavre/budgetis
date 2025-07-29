from django.contrib import admin

from .models import AvailableYear


@admin.register(AvailableYear)
class AvailableYearAdmin(admin.ModelAdmin):
    list_display = ("year", "type", "created_at")
    list_filter = ("type",)
    ordering = ("-year",)
    list_display_links = ("year",)
