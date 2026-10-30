"""Correct Sankey settings only; account rows and amounts are never changed."""

from django.db import migrations


MCH2 = "mch2"
SALARIES = "Salaires"
GOODS = "Biens et services"
INTERCOS = "Autres intercommunalités"
INTEREST = "Intérêts (charges)"
TAXES = "Taxes (usage)"
DOTATIONS = "Amortissements et attributions"
OTHER_COMMUNE = "Autres commune"

CODE_RULES = (
    ("82000", "3612", "06", INTERCOS),
    ("82000", "3612", "07", INTERCOS),
    # ACP purchases and corresponding sales share a category: the Sankey
    # shows their net cost instead of inflating both sides by CHF 199,000.
    ("82000", "3612", "55", GOODS),
    ("82000", "4250", "55", GOODS),
)
FINANCIAL_RANGES = (
    (3410, 3419, OTHER_COMMUNE),
    (3420, 3429, GOODS),
    (3430, 3439, GOODS),
    (3440, 3449, DOTATIONS),
    (3490, 3499, OTHER_COMMUNE),
)
RANGE_PRIORITY = 50


def correct_rules(apps, schema_editor):
    category_model = apps.get_model("finance", "SankeyCategory")
    code_rule_model = apps.get_model("finance", "SankeyAccountCodeRule")
    range_rule_model = apps.get_model("finance", "SankeyNatureRangeRule")
    alias = schema_editor.connection.alias
    categories = {category.name: category.pk for category in category_model.objects.using(alias).all()}
    rules = code_rule_model.objects.using(alias).filter(scheme=MCH2)

    # These historical salary mappings override the intentional 39xx gap.
    rules.filter(function__in=("02100", "02210"), nature="3910", category_id=categories[SALARIES]).delete()
    # A wildcard wins before some specific subaccounts in the current resolver.
    # Remove it so forestry rules and the ACP exception are unambiguous.
    rules.filter(function="82000", nature="3612", sub_account="", category_id=categories[GOODS]).delete()

    for function, nature, sub_account, category in CODE_RULES:
        code_rule_model.objects.using(alias).update_or_create(
            scheme=MCH2,
            function=function,
            nature=nature,
            sub_account=sub_account,
            defaults={"category_id": categories[category]},
        )

    # Water sales are usage fees, including the wildcard's subaccounts.
    rules.filter(function="71000", nature="4240", sub_account="").update(category_id=categories[TAXES])

    range_rule_model.objects.using(alias).filter(
        scheme=MCH2, nature_start=3400, nature_end=3499, category_id=categories[INTEREST]
    ).update(nature_end=3409)
    for start, end, category in FINANCIAL_RANGES:
        range_rule_model.objects.using(alias).update_or_create(
            scheme=MCH2,
            nature_start=start,
            nature_end=end,
            category_id=categories[category],
            defaults={"priority": RANGE_PRIORITY},
        )


class Migration(migrations.Migration):
    dependencies = [("finance", "0010_alter_sankeycategory_color_alter_sankeycategory_name_and_more")]
    operations = [migrations.RunPython(correct_rules, migrations.RunPython.noop)]
