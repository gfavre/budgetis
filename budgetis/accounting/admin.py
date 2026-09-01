from django.contrib import admin
from django.contrib.admin import helpers
from django.db.models import CharField
from django.db.models import F
from django.db.models import Q
from django.db.models import Value
from django.db.models.functions import Cast
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django.template.response import TemplateResponse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .forms import AccountGroupForm
from .forms import ReassignAccountResponsibleForm
from .forms import ReassignGroupResponsibleForm
from .models import Account
from .models import AccountCodeMapping
from .models import AccountComment
from .models import AccountGroup
from .models import GroupResponsibility


REASSIGN_RESPONSIBLE_TEMPLATE = "accounting/admin/reassign_responsible.html"


def _reassign_responsible_response(model_admin, request, queryset, form, title):
    context = {
        **model_admin.admin_site.each_context(request),
        "title": title,
        "queryset": queryset,
        "form": form,
        "opts": model_admin.opts,
        "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
    }
    return TemplateResponse(request, REASSIGN_RESPONSIBLE_TEMPLATE, context)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        "full_code_display",
        "label",
        "year",
        "is_budget",
        "report_status",
        "updated_at",
    )
    list_filter = ("year", "is_budget", "visible_in_report", "updated_at")
    search_fields = ("label",)
    date_hierarchy = "updated_at"
    actions = ["hide_from_report", "show_in_report", "reassign_responsible"]
    ordering = ()  # Important: prevent default ordering

    @admin.display(ordering="full_code_sort", description=_("Code"))
    def full_code_display(self, obj):
        return obj.full_code

    @admin.action(description=_("Hide accounts in report"))
    def hide_from_report(self, request, queryset):
        queryset.update(visible_in_report=False)

    @admin.action(description=_("Display accounts in report"))
    def show_in_report(self, request, queryset):
        queryset.update(visible_in_report=True)

    @admin.action(description=_("Reassign responsible"))
    def reassign_responsible(self, request, queryset):
        if "apply" in request.POST:
            form = ReassignAccountResponsibleForm(request.POST)
            if form.is_valid():
                responsible = form.cleaned_data["responsible"]
                pairs = {(a.group_id, a.year) for a in queryset if a.group_id}
                for group_id, year in pairs:
                    GroupResponsibility.objects.update_or_create(
                        group_id=group_id, year=year, defaults={"responsible": responsible}
                    )
                self.message_user(request, _("Updated %(count)d group(s).") % {"count": len(pairs)})
                return None
        else:
            form = ReassignAccountResponsibleForm()

        return _reassign_responsible_response(self, request, queryset, form, _("Reassign responsible"))

    @admin.display(description="Rapport")
    def report_status(self, obj):
        if obj.visible_in_report:
            return "✔️"
        return format_html('<span style="color: red; text-decoration: line-through;">❌ Masqué</span>')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            full_code_sort=Concat(
                Cast(F("function"), output_field=CharField()),
                Value("."),
                Cast(F("nature"), output_field=CharField()),
                Value("."),
                Cast(Coalesce(F("sub_account"), Value("")), output_field=CharField()),
            )
        )

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
    list_display = ("code", "label", "scheme", "level", "parent", "updated_at")
    list_filter = ("scheme", "level", "updated_at")
    date_hierarchy = "updated_at"
    search_fields = ("label", "code")
    actions = ["reassign_responsible"]
    autocomplete_fields = ("parent",)
    search_help_text = _("Code or label")

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

    @admin.action(description=_("Reassign responsible"))
    def reassign_responsible(self, request, queryset):
        if "apply" in request.POST:
            form = ReassignGroupResponsibleForm(request.POST)
            if form.is_valid():
                responsible = form.cleaned_data["responsible"]
                year = int(form.cleaned_data["year"])
                for group in queryset:
                    GroupResponsibility.objects.update_or_create(
                        group=group, year=year, defaults={"responsible": responsible}
                    )
                self.message_user(request, _("Updated %(count)d group(s).") % {"count": queryset.count()})
                return None
        else:
            form = ReassignGroupResponsibleForm()

        return _reassign_responsible_response(self, request, queryset, form, _("Reassign responsible"))


@admin.register(GroupResponsibility)
class GroupResponsibilityAdmin(admin.ModelAdmin):
    list_display = ("group", "year", "responsible")
    list_filter = ("year", "group__scheme", "responsible")
    search_fields = ("group__label", "responsible__name", "responsible__email", "responsible__trigram")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "responsible":
            formfield.label_from_instance = lambda obj: str(obj)
        return formfield

    def get_queryset(self, request):
        # Override to prefetch related groups for performance
        return super().get_queryset(request).select_related("group", "responsible")


@admin.register(AccountCodeMapping)
class AccountCodeMappingAdmin(admin.ModelAdmin):
    list_display = ("mch1_code", "mch2_code")
    search_fields = (
        "mch1_function",
        "mch1_nature",
        "mch1_sub_account",
        "mch2_function",
        "mch2_nature",
        "mch2_sub_account",
    )
