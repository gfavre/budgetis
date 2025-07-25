from django import forms
from django.contrib.admin import widgets as admin_widgets

from .models import Account
from .models import AccountGroup
from .models import MetaGroup
from .models import SuperGroup


class AccountGroupForm(forms.ModelForm):
    accounts = forms.ModelMultipleChoiceField(
        queryset=Account.objects.order_by("function", "nature", "sub_account"),
        required=False,
        widget=admin_widgets.FilteredSelectMultiple("Accounts", is_stacked=False),
    )

    class Meta:
        model = AccountGroup
        fields = ("id", "code", "label", "accounts")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["accounts"].initial = self.instance.accounts.all()


class SuperGroupForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=AccountGroup.objects.order_by("code"),
        required=False,
        widget=admin_widgets.FilteredSelectMultiple("AccountGroup", is_stacked=False),
    )

    class Meta:
        model = SuperGroup
        fields = ("id", "code", "label", "groups")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["groups"].initial = self.instance.groups.all()


class MetaGroupForm(forms.ModelForm):
    supergroups = forms.ModelMultipleChoiceField(
        queryset=SuperGroup.objects.order_by("code"),
        required=False,
        widget=admin_widgets.FilteredSelectMultiple("SuperGroup", is_stacked=False),
    )

    class Meta:
        model = MetaGroup
        fields = ("id", "code", "label", "supergroups")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["supergroups"].initial = self.instance.supergroups.all()
