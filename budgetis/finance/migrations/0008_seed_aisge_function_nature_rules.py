"""
Nature 3612 ("Parts aux communes et associations intercommunales") is shared
by several unrelated MCH2 payees - AISGE, APEC, RAT, Crèches, Trav. Social...
- distinguishable only by which function (administrative unit) pays. AISGE
specifically spans three function families: 218x, 219x, 433x.

This also corrects a real error surfaced while adding these rules: 0005
derived an exact-code rule mapping function 21800 (nature 3612, "UAPE") to
RAT. That happened because RAT's MCH1 rule (400_seed_sankey_rules) matches
*any* sub-account of 710.365 - a deliberately preserved MCH1 bug (see that
migration's comment) - and accounting.AccountCodeMapping has three different
MCH2 codes (21800.3612, 54400.3632, 54500.3612) all crosswalking back to that
same MCH1 710.365 code under different sub-accounts. Re-resolving each of
those three against the (bug-preserving) MCH1 rule stamped "RAT" onto all
three, even though only one of them is actually RAT. This migration removes
the 21800.3612 one specifically, since the new function+nature rule below
already reclassifies it correctly as AISGE; the other two (54400.3632
"Trav. Social", 54500.3612 "Crèches") are left as later follow-up.
"""

from django.db import migrations


MCH2 = "mch2"

# (function_prefix, nature_start, nature_end, category_name)
FUNCTION_NATURE_RULES = [
    ("218", 3612, 3612, "AISGE"),
    ("219", 3612, 3612, "AISGE"),
    ("433", 3612, 3612, "AISGE"),
]

# (function, nature, sub_account, category_name) - see module docstring.
WRONG_CODE_RULES = [
    ("21800", "3612", "", "RAT"),
]


def seed_function_nature_rules(apps, schema_editor):
    SankeyCategory = apps.get_model("finance", "SankeyCategory")
    SankeyFunctionNatureRule = apps.get_model("finance", "SankeyFunctionNatureRule")
    SankeyAccountCodeRule = apps.get_model("finance", "SankeyAccountCodeRule")

    categories = {category.name: category for category in SankeyCategory.objects.all()}

    for function, nature, sub_account, category_name in WRONG_CODE_RULES:
        SankeyAccountCodeRule.objects.filter(
            scheme=MCH2, function=function, nature=nature, sub_account=sub_account, category=categories[category_name]
        ).delete()

    for function_prefix, nature_start, nature_end, category_name in FUNCTION_NATURE_RULES:
        SankeyFunctionNatureRule.objects.get_or_create(
            scheme=MCH2,
            function_prefix=function_prefix,
            nature_start=nature_start,
            nature_end=nature_end,
            category=categories[category_name],
        )


def unseed_function_nature_rules(apps, schema_editor):
    SankeyFunctionNatureRule = apps.get_model("finance", "SankeyFunctionNatureRule")
    SankeyFunctionNatureRule.objects.filter(
        scheme=MCH2, function_prefix__in=[rule[0] for rule in FUNCTION_NATURE_RULES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0007_sankeyfunctionnaturerule"),
    ]

    operations = [
        migrations.RunPython(seed_function_nature_rules, unseed_function_nature_rules),
    ]
