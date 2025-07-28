from django.contrib import admin
from django.db.models import Q
from django.utils.html import format_html
from django.utils.html import format_html_join

from .forms import AccountGroupForm
from .forms import MetaGroupForm
from .forms import SuperGroupForm
from .models import Account
from .models import AccountComment
from .models import AccountGroup
from .models import GroupResponsibility
from .models import MetaGroup
from .models import SuperGroup


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        "full_code",
        "year",
        "is_budget",
        "updated_at",
    )
    list_filter = ("year", "is_budget", "group", "updated_at")
    search_fields = ("label",)
    date_hierarchy = "updated_at"

    def get_search_results(self, request, queryset, search_term):
        # base search
        queryset, use_distinct = super().get_search_results(
            request,
            queryset,
            search_term,
        )

        # Match function.nature or variants
        if "." in search_term:
            parts = search_term.split(".")
            try:
                function = int(parts[0])
            except ValueError:
                return queryset, use_distinct  # skip bad input

            if len(parts) == 1 or parts[1] == "":
                # User typed "170."
                queryset |= self.model.objects.filter(function=function)
            else:
                try:
                    nature = int(parts[1])
                    queryset |= self.model.objects.filter(function=function, nature=nature)
                except ValueError:
                    pass
        else:
            # User typed e.g. "170" → match function or nature
            try:
                value = int(search_term)
                queryset |= self.model.objects.filter(Q(function=value) | Q(nature=value))
            except ValueError:
                pass

        return queryset, use_distinct


@admin.register(AccountComment)
class AccountCommentAdmin(admin.ModelAdmin):
    date_hierarchy = "created_at"
    list_display = ("account", "author", "created_at")
    list_filter = ("author", "created_at")
    raw_id_fields = ("account",)
    search_fields = ("content", "account__label")

    def get_queryset(self, request):
        # Override to prefetch related accounts for performance
        return super().get_queryset(request).select_related("account")

    def get_search_results(self, request, queryset, search_term):
        # base search
        queryset, use_distinct = super().get_search_results(
            request,
            queryset,
            search_term,
        )

        # Match function.nature or variants
        if "." in search_term:
            parts = search_term.split(".")
            try:
                function = int(parts[0])
            except ValueError:
                return queryset, use_distinct  # skip bad input

            if len(parts) == 1 or parts[1] == "":
                # User typed "170."
                queryset |= self.model.objects.filter(account__function=function)
            else:
                try:
                    nature = int(parts[1])
                    queryset |= self.model.objects.filter(account__function=function, account__nature=nature)
                except ValueError:
                    pass
        else:
            # User typed e.g. "170" → match function or nature
            try:
                value = int(search_term)
                queryset |= self.model.objects.filter(Q(account__function=value) | Q(account__nature=value))
            except ValueError:
                pass

        return queryset, use_distinct


@admin.register(AccountGroup)
class AccountGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "updated_at")
    list_filter = ("supergroup", "updated_at")
    date_hierarchy = "updated_at"
    search_fields = ("label", "code")

    form = AccountGroupForm

    def save_model(self, request, obj, form, change):
        # Save the group first
        super().save_model(request, obj, form, change)

        # Update selected accounts
        selected_accounts = form.cleaned_data.get("accounts", [])
        selected_ids = {a.id for a in selected_accounts}

        # Remove accounts no longer in the selection
        Account.objects.filter(group=obj).exclude(id__in=selected_ids).update(group=None)

        # Assign the selected accounts to this group
        for account in selected_accounts:
            if account.group_id != obj.id:
                account.group = obj
                account.save()


@admin.register(GroupResponsibility)
class GroupResponsibilityAdmin(admin.ModelAdmin):
    list_display = ("group", "year", "responsible")
    list_filter = ("year", "group__supergroup", "responsible")
    search_fields = ("group__label", "responsible__name", "responsible__email", "responsible__trigram")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "responsible":
            formfield.label_from_instance = lambda obj: str(obj)
        return formfield

    def get_queryset(self, request):
        # Override to prefetch related groups for performance
        return super().get_queryset(request).select_related("group", "responsible")


@admin.register(SuperGroup, site=admin.site)
class SuperGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "get_groups")
    list_filter = ("updated_at",)
    date_hierarchy = "updated_at"
    search_fields = ("label", "code")

    form = SuperGroupForm

    def get_queryset(self, request):
        # Override to prefetch related groups for performance
        return super().get_queryset(request).prefetch_related("groups")

    @admin.display(description="Groupes")
    def get_groups(self, obj):
        return format_html("<ul>{}</ul>", format_html_join("", "<li>{}</li>", ((str(e),) for e in obj.groups.all())))

    def save_model(self, request, obj, form, change):
        # Save the group first
        super().save_model(request, obj, form, change)

        selected_groups = form.cleaned_data.get("groups", [])
        selected_ids = {a.id for a in selected_groups}

        # Remove accounts no longer in the selection
        AccountGroup.objects.filter(supergroup=obj).exclude(id__in=selected_ids).update(supergroup=None)

        # Assign the selected accounts to this group
        for group in selected_groups:
            if group.supergroup_id != obj.id:
                group.supergroup = obj
                group.save()


@admin.register(MetaGroup, site=admin.site)
class MetaGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "get_supergroups")
    list_filter = ("updated_at",)
    date_hierarchy = "updated_at"
    search_fields = ("label", "code")

    form = MetaGroupForm

    def get_queryset(self, request):
        # Override to prefetch related supergroups for performance
        return super().get_queryset(request).prefetch_related("supergroups")

    @admin.display(description="Supergroupes")
    def get_supergroups(self, obj):
        return format_html(
            "<ul>{}</ul>", format_html_join("", "<li>{}</li>", ((str(e),) for e in obj.supergroups.all()))
        )

    def save_model(self, request, obj, form, change):
        # Save the group first
        super().save_model(request, obj, form, change)

        selected_groups = form.cleaned_data.get("supergroups", [])
        selected_ids = {a.id for a in selected_groups}

        # Remove accounts no longer in the selection
        SuperGroup.objects.filter(metagroup=obj).exclude(id__in=selected_ids).update(metagroup=None)

        # Assign the selected accounts to this group
        for supergroup in selected_groups:
            if supergroup.metagroup_id != obj.id:
                supergroup.metagroup = obj
                supergroup.save()
