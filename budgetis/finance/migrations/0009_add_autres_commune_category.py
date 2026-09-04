"""
Commune has no generic "Autres" catch-all, unlike Revenue ("Autres recettes")
and Intercommunality ("Autres intercommunalités") - so any commune-flow
account outside Salaires/Biens et services/Intérêts (charges)/Aides et
subventions was silently dropped from the diagram. The one real, unambiguous
gap is MCH2's official NatureGroup 38 "Charges extraordinaires" (3800-3899):
it doesn't overlap any other commune category's range.

Canton does NOT get an equivalent catch-all here: Canton's known payments
(Police, Péréquation, Sécurité sociale) and Intercommunality's share the same
nature family (NatureGroup 36 "Charges de transferts" - see 0008's AISGE
rules), so an unidentified 36xx code can't be routed to "Autres canton" vs
"Autres intercommunalités" by nature alone. It keeps falling into the
existing intercommunality catch-all, as before.
"""

from django.db import migrations


MCH2 = "mch2"

CATEGORY_NAME = "Autres commune"
CATEGORY_FLOW = "commune"
CATEGORY_COLOR = "#C9A66B"
CATEGORY_ORDER = 4


def add_autres_commune(apps, schema_editor):
    SankeyCategory = apps.get_model("finance", "SankeyCategory")
    SankeyNatureRangeRule = apps.get_model("finance", "SankeyNatureRangeRule")

    category, _created = SankeyCategory.objects.get_or_create(
        name=CATEGORY_NAME,
        defaults={"flow": CATEGORY_FLOW, "color": CATEGORY_COLOR, "order": CATEGORY_ORDER},
    )
    SankeyNatureRangeRule.objects.get_or_create(
        scheme=MCH2, nature_start=3800, nature_end=3899, category=category, defaults={"priority": 200}
    )


def remove_autres_commune(apps, schema_editor):
    SankeyCategory = apps.get_model("finance", "SankeyCategory")
    SankeyCategory.objects.filter(name=CATEGORY_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0008_seed_aisge_function_nature_rules"),
    ]

    operations = [
        migrations.RunPython(add_autres_commune, remove_autres_commune),
    ]
