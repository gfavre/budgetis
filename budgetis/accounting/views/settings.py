from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView
from django.views.generic import DeleteView
from django.views.generic import ListView
from django.views.generic import UpdateView

from budgetis.accounting.models import MCH2_GROUP_CODE_LENGTH
from budgetis.accounting.models import Account
from budgetis.accounting.models import AccountGroup
from budgetis.accounting.models import FunctionSplit
from budgetis.accounting.models import GroupResponsibility
from budgetis.accounting.settings_forms import FUNCTION_CATEGORY_PREFIX
from budgetis.accounting.settings_forms import FunctionCategoryFormSet
from budgetis.accounting.settings_forms import FunctionSplitSettingsForm
from budgetis.accounting.settings_forms import ResponsibilitySettingsForm
from budgetis.common.models import ChartScheme
from budgetis.users.permissions import PlatformSettingsMixin


SETTINGS_PAGE_SIZE = 25
RESPONSIBILITY_URL = "accounting:responsibility-settings"
SPLIT_URL = "accounting:function-split-settings"


class ResponsibilitySettingsView(PlatformSettingsMixin, ListView):
    template_name = "accounting/settings/responsibilities.html"
    context_object_name = "assignments"
    paginate_by = SETTINGS_PAGE_SIZE

    def get_queryset(self):
        queryset = GroupResponsibility.objects.select_related("group", "responsible").order_by(
            "-year", "group__scheme", "group__code", "function"
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(group__code__icontains=query)
                | Q(group__label__icontains=query)
                | Q(function__icontains=query)
                | Q(responsible__trigram__icontains=query)
            )
        year = self.request.GET.get("year", "")
        if year.isascii() and year.isdigit():
            queryset = queryset.filter(year=int(year))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["years"] = GroupResponsibility.objects.values_list("year", flat=True).distinct().order_by("-year")
        return context


class ResponsibilityCreateView(PlatformSettingsMixin, CreateView):
    model = GroupResponsibility
    form_class = ResponsibilitySettingsForm
    template_name = "accounting/settings/responsibility_form.html"
    success_url = reverse_lazy(RESPONSIBILITY_URL)

    def form_valid(self, form):
        messages.success(self.request, _("Responsibility saved."))
        return super().form_valid(form)


class ResponsibilityUpdateView(PlatformSettingsMixin, UpdateView):
    model = GroupResponsibility
    form_class = ResponsibilitySettingsForm
    template_name = "accounting/settings/responsibility_form.html"
    success_url = reverse_lazy(RESPONSIBILITY_URL)

    def form_valid(self, form):
        messages.success(self.request, _("Responsibility saved."))
        return super().form_valid(form)


class ResponsibilityDeleteView(PlatformSettingsMixin, DeleteView):
    model = GroupResponsibility
    template_name = "accounting/settings/responsibility_confirm_delete.html"
    success_url = reverse_lazy(RESPONSIBILITY_URL)


class FunctionSplitSettingsView(PlatformSettingsMixin, ListView):
    template_name = "accounting/settings/function_splits.html"
    context_object_name = "groups"
    paginate_by = SETTINGS_PAGE_SIZE

    def get_queryset(self):
        queryset = (
            AccountGroup.objects.filter(scheme=ChartScheme.MCH2, level=MCH2_GROUP_CODE_LENGTH)
            .select_related("function_split")
            .order_by("code")
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(code__icontains=query) | Q(label__icontains=query))
        return queryset


class FunctionSplitUpdateView(PlatformSettingsMixin, View):
    template_name = "accounting/settings/function_split_form.html"

    def _configuration(self, group_id):
        group = get_object_or_404(AccountGroup, pk=group_id, scheme=ChartScheme.MCH2, level=MCH2_GROUP_CODE_LENGTH)
        split = FunctionSplit.objects.filter(group=group).first() or FunctionSplit(group=group, enabled=False)
        configured = set(split.categories.values_list("function", flat=True)) if split.pk else set()
        functions = (
            Account.objects.filter(group=group).values_list("function", flat=True).distinct().order_by("function")
        )
        initial = [{"function": function} for function in functions if function not in configured]
        return group, split, initial

    def _forms(self, group_id, data=None):
        group, split, initial = self._configuration(group_id)
        form = FunctionSplitSettingsForm(data, instance=split)
        formset = FunctionCategoryFormSet(data, instance=split, prefix=FUNCTION_CATEGORY_PREFIX, initial=initial)
        formset.extra = len(initial) + 1
        return {"group": group, "form": form, "formset": formset}

    def get(self, request, group_id):
        return render(request, self.template_name, self._forms(group_id))

    def post(self, request, group_id):
        context = self._forms(group_id, request.POST)
        form, formset = context["form"], context["formset"]
        form_valid = form.is_valid()
        formset_valid = formset.is_valid()
        if form_valid and formset_valid:
            formset.instance = form.save()
            formset.save()
            messages.success(request, _("Group presentation saved."))
            return redirect(SPLIT_URL)
        return render(request, self.template_name, context)
