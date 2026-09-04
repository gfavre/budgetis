from django.db import migrations


MCH1 = "mch1"
MCH2 = "mch2"

# ----- Categories --------------------------------------------------------
# name -> (flow, color, order). Scheme-agnostic: MCH1 and MCH2 both feed the
# same bucket identities, only the rules resolving accounts into them differ.
CATEGORIES = [
    ("Impôts (général)", "revenue", "#246BCE", 0),
    ("Impôts aléatoires", "revenue", "#5B9BD6", 1),
    ("Taxes (usage)", "revenue", "#F57C00", 2),
    ("Locations", "revenue", "#6D4C41", 3),
    ("Intérêts (revenus)", "revenue", "#9E9E9E", 4),
    ("Autres recettes", "revenue", "#AAAAAA", 5),
    ("Prélèvements sur fonds", "revenue", "#6366F1", 6),
    ("Sécurité sociale", "canton", "#6DA44D", 0),
    ("Péréquation", "canton", "#2E5A20", 1),
    ("Police", "canton", "#8BC06C", 2),
    ("AISGE", "intercommunality", "#94402D", 0),
    ("APEC", "intercommunality", "#B55239", 1),
    ("Transports région", "intercommunality", "#CD6E4D", 2),
    ("RAT", "intercommunality", "#B97258", 3),
    ("Autres intercommunalités", "intercommunality", "#E7A38C", 4),
    ("Salaires", "commune", "#D4AF37", 0),
    ("Biens et services", "commune", "#E7C970", 1),
    ("Intérêts (charges)", "commune", "#D4C07E", 2),
    ("Aides et subventions", "commune", "#D4A337", 3),
    ("Amortissements et attributions", "dotation", "#D49C37", 0),
]

# ----- MCH1 rules ----------------------------------------------------------
# A direct, verbatim port of the constants previously hardcoded in
# budgetis/finance/builders.py (see git history) - not a redesign, just moved
# from Python constants to database rows.

MCH1_NATURE_RANGES = [
    # (nature_start, nature_end, priority, category)
    (402, 402, 10, "Impôts aléatoires"),
    (404, 404, 10, "Impôts aléatoires"),
    (405, 405, 10, "Impôts aléatoires"),
    (400, 409, 50, "Impôts (général)"),
    (430, 439, 50, "Taxes (usage)"),
    (422, 422, 50, "Intérêts (revenus)"),
    (424, 424, 50, "Intérêts (revenus)"),
    (423, 423, 50, "Locations"),
    (425, 425, 50, "Locations"),
    (427, 427, 50, "Locations"),
    (480, 489, 50, "Prélèvements sur fonds"),
    (400, 499, 200, "Autres recettes"),
    (300, 309, 50, "Salaires"),
    (310, 319, 50, "Biens et services"),
    (320, 329, 50, "Intérêts (charges)"),
    (360, 369, 50, "Aides et subventions"),
    (350, 359, 200, "Autres intercommunalités"),
    (330, 349, 50, "Amortissements et attributions"),
    (370, 399, 50, "Amortissements et attributions"),
]

# (function, nature, sub_account, category)
# NB: the old hardcoded matcher (`q_from_code` in builders.py, pre-rewrite)
# looked up a field named "subaccount" that doesn't exist on Account (the real
# field is "sub_account") - the lookup always raised and was silently caught,
# so a sub-account-qualified code like "710.365.1" actually matched *any*
# sub-account under that function+nature. Blank sub_account here reproduces
# that real, verified behavior (see the parity check against live 2025 data
# run during this change) rather than the narrower behavior the code intended.
MCH1_ACCOUNT_CODES = [
    ("720", "351", "", "Sécurité sociale"),
    ("220", "352", "", "Péréquation"),
    ("600", "351", "", "Police"),
    ("500", "352", "", "AISGE"),
    ("510", "352", "", "AISGE"),
    ("510", "366", "", "AISGE"),
    ("520", "352", "", "AISGE"),
    ("520", "366", "", "AISGE"),
    ("530", "351", "", "AISGE"),
    ("530", "451", "", "AISGE"),
    ("550", "352", "", "AISGE"),
    ("560", "352", "", "AISGE"),
    ("570", "352", "", "AISGE"),
    ("460", "352", "", "APEC"),
    ("180", "351", "", "Transports région"),
    ("710", "365", "", "RAT"),
]

# ----- MCH2 rules -----------------------------------------------------------
# A coarse, low-priority fallback only - the bulk of MCH2 coverage comes from
# 0005, which derives exact-code MCH2 rules from these MCH1 rules via
# accounting.AccountCodeMapping. These nature ranges and label rules exist to
# catch MCH2 accounts with no MCH1 predecessor in that crosswalk (e.g. new
# 2027 budget lines) - not final, meant to be refined via admin.

MCH2_NATURE_RANGES = [
    (3000, 3099, 50, "Salaires"),
    (3100, 3199, 50, "Biens et services"),
    (3300, 3399, 50, "Amortissements et attributions"),
    (3400, 3499, 50, "Intérêts (charges)"),
    (3600, 3699, 200, "Autres intercommunalités"),
    (4000, 4099, 50, "Impôts (général)"),
    (4200, 4299, 50, "Taxes (usage)"),
    (4400, 4499, 50, "Intérêts (revenus)"),
    (4600, 4699, 200, "Autres recettes"),
]

MCH2_ACCOUNT_CODES = [
    ("93001", "3621", "", "Sécurité sociale"),
    ("93000", "3622", "", "Péréquation"),
    ("11100", "3611", "", "Police"),
]

MCH2_LABEL_RULES = [
    ("AISGE", "AISGE"),
    ("APEC", "APEC"),
]


def seed_sankey_rules(apps, schema_editor):
    SankeyCategory = apps.get_model("finance", "SankeyCategory")
    SankeyNatureRangeRule = apps.get_model("finance", "SankeyNatureRangeRule")
    SankeyAccountCodeRule = apps.get_model("finance", "SankeyAccountCodeRule")
    SankeyLabelRule = apps.get_model("finance", "SankeyLabelRule")

    categories = {}
    for name, flow, color, order in CATEGORIES:
        categories[name], _created = SankeyCategory.objects.get_or_create(
            name=name, defaults={"flow": flow, "color": color, "order": order}
        )

    for nature_start, nature_end, priority, category_name in MCH1_NATURE_RANGES:
        SankeyNatureRangeRule.objects.get_or_create(
            scheme=MCH1,
            nature_start=nature_start,
            nature_end=nature_end,
            category=categories[category_name],
            defaults={"priority": priority},
        )
    for function, nature, sub_account, category_name in MCH1_ACCOUNT_CODES:
        SankeyAccountCodeRule.objects.get_or_create(
            scheme=MCH1,
            function=function,
            nature=nature,
            sub_account=sub_account,
            defaults={"category": categories[category_name]},
        )

    for nature_start, nature_end, priority, category_name in MCH2_NATURE_RANGES:
        SankeyNatureRangeRule.objects.get_or_create(
            scheme=MCH2,
            nature_start=nature_start,
            nature_end=nature_end,
            category=categories[category_name],
            defaults={"priority": priority},
        )
    for function, nature, sub_account, category_name in MCH2_ACCOUNT_CODES:
        SankeyAccountCodeRule.objects.get_or_create(
            scheme=MCH2,
            function=function,
            nature=nature,
            sub_account=sub_account,
            defaults={"category": categories[category_name]},
        )
    for pattern, category_name in MCH2_LABEL_RULES:
        SankeyLabelRule.objects.get_or_create(
            scheme=MCH2, pattern=pattern, defaults={"category": categories[category_name]}
        )


def unseed_sankey_rules(apps, schema_editor):
    SankeyCategory = apps.get_model("finance", "SankeyCategory")
    SankeyCategory.objects.filter(name__in=[name for name, *_ in CATEGORIES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0003_sankeycategory_sankeylabelrule_sankeynaturerangerule_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_sankey_rules, unseed_sankey_rules),
    ]
