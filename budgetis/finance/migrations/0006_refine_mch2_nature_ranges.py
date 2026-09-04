"""
Closes MCH2 coverage gaps using the canton's official nature classification
(accounting.NatureGroup, imported from the canton's reference file) rather
than the codes happening to appear in accounting.AccountCodeMapping (0005):
that crosswalk only knows the MCH1<->MCH2 codes actually used historically, so
a nature family with no MCH1 predecessor (e.g. group 35 "Attributions aux
fonds", never itemized under MCH1) silently dropped its accounts from the
diagram - and any *future* code added under an existing family (say, a new
leaf under "30 Charges de personnel") would too, since it can't already be in
that historical crosswalk.

Boundaries below were read from NatureGroup's official group codes, not
guessed. As before, these are a coarse fallback: exact-code rules from 0005
and the label rules from 0004 always take precedence over any of them.
"""

from django.db import migrations


MCH2 = "mch2"

# (nature_start, nature_end, priority, category_name)
NEW_RANGES = [
    (3500, 3599, 50, "Amortissements et attributions"),  # NatureGroup 35 - Attributions aux fonds et fin. spéciaux
    (3700, 3799, 50, "Aides et subventions"),  # NatureGroup 37 - Subventions redistribuées
    # Universal revenue catch-all, mirrors MCH1's 400-499 sweep - stops at 4899
    # to exclude NatureGroup 49 "Imputations internes", just like the charges
    # side leaves 3900-3999 unmapped: those are accounting offsets, not flows.
    (4000, 4899, 200, "Autres recettes"),
    (4400, 4409, 50, "Intérêts (revenus)"),  # NatureGroup 440 - Revenus des intérêts only
    (4430, 4439, 50, "Locations"),  # NatureGroup 443 - Produits des immeubles PF
    (4470, 4479, 50, "Locations"),  # NatureGroup 447 - Produit des immeubles PA
    (4480, 4489, 50, "Locations"),  # NatureGroup 448 - Revenus des immeubles loués
    (4500, 4599, 50, "Prélèvements sur fonds"),  # NatureGroup 45 - Prélèvements sur les fonds
    (4021, 4021, 10, "Impôts aléatoires"),  # Impôts fonciers - MCH1 verbatim-ported 402 equivalent
    (4023, 4023, 10, "Impôts aléatoires"),  # Droits de mutation - MCH1 verbatim-ported 404 equivalent
    (4024, 4024, 10, "Impôts aléatoires"),  # Successions et donations - MCH1 verbatim-ported 405 equivalent
]

# Rules being replaced by a finer split above: the old (4400, 4499) block
# swallowed dividends/capital gains/rentals that aren't interest, and the old
# (4600, 4699) block is now fully subsumed by the universal 4000-4999 sweep.
SUPERSEDED_RANGES = [
    (4400, 4499, "Intérêts (revenus)"),
    (4600, 4699, "Autres recettes"),
]


def refine_mch2_nature_ranges(apps, schema_editor):
    SankeyCategory = apps.get_model("finance", "SankeyCategory")
    SankeyNatureRangeRule = apps.get_model("finance", "SankeyNatureRangeRule")

    categories = {category.name: category for category in SankeyCategory.objects.all()}

    for nature_start, nature_end, category_name in SUPERSEDED_RANGES:
        SankeyNatureRangeRule.objects.filter(
            scheme=MCH2, nature_start=nature_start, nature_end=nature_end, category=categories[category_name]
        ).delete()

    for nature_start, nature_end, priority, category_name in NEW_RANGES:
        SankeyNatureRangeRule.objects.get_or_create(
            scheme=MCH2,
            nature_start=nature_start,
            nature_end=nature_end,
            category=categories[category_name],
            defaults={"priority": priority},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0005_derive_mch2_rules_from_account_code_mapping"),
    ]

    operations = [
        # Not reversed: this migration only tightens/adds MCH2 fallback ranges
        # beneath the exact-code and label rules, which always win regardless -
        # reversing would just reintroduce known coverage gaps.
        migrations.RunPython(refine_mch2_nature_ranges, migrations.RunPython.noop),
    ]
