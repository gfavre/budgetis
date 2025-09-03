from django import forms
from django.contrib import admin

from .models import SiteConfiguration


class SiteConfigurationForm(forms.ModelForm):
    class Meta:
        model = SiteConfiguration
        fields = "__all__"  # noqa: DJ007
        widgets = {
            "gradient_start": forms.TextInput(attrs={"type": "color"}),
            "gradient_end": forms.TextInput(attrs={"type": "color"}),
        }


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(admin.ModelAdmin):
    form = SiteConfigurationForm

    def has_add_permission(self, request):
        # Prevent creating multiple instances
        return not SiteConfiguration.objects.exists()
