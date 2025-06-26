from django.contrib import admin

from .models import Account


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        "year",
        "function",
        "nature",
        "sub_account",
        "label",
        "is_budget",
        "updated_at",
    )
    list_filter = ("year", "is_budget", "group")
    search_fields = ("label",)
    date_hierarchy = "updated_at"

    def get_search_results(self, request, queryset, search_term):
        # base search
        queryset, use_distinct = super().get_search_results(
            request,
            queryset,
            search_term,
        )

        # try matching function.nature like 170.303
        if "." in search_term:
            try:
                function_str, nature_str = search_term.strip().split(".")
                function = int(function_str)
                nature = int(nature_str)
                queryset |= self.model.objects.filter(function=function, nature=nature)
            except ValueError:
                pass  # ignore if invalid format

        return queryset, use_distinct
