"""
Prepopulates MCH2 Sankey account-code rules by walking every MCH1 <-> MCH2
crosswalk row in accounting.AccountCodeMapping and re-resolving each MCH1
code against the already-seeded MCH1 rules (0004): whatever category an MCH1
code lands in, its MCH2 equivalent is seeded to land in the same category.

This exists because MCH1 nature -> MCH2 nature is NOT a clean mapping (most
MCH1 natures fan out to several different MCH2 natures depending on the
account's function - e.g. 311 maps to 10 different MCH2 natures), so a
nature-range guess for MCH2 can't be derived reliably. An exact-code crosswalk
can, since it is resolved per real account rather than per nature bucket.

The broad MCH2_NATURE_RANGES / MCH2_LABEL_RULES seeded in 0004 remain as a
lower-priority fallback for MCH2 accounts that have no MCH1 predecessor in the
crosswalk (e.g. genuinely new 2027 budget lines).
"""

from django.db import migrations


MCH1 = "mch1"
MCH2 = "mch2"


def _resolve_mch1_category_id(function: str, nature: str, sub_account: str, code_rules, range_rules) -> int | None:
    for rule in code_rules:
        if (
            rule.function == function
            and rule.nature == nature
            and (not rule.sub_account or rule.sub_account == sub_account)
        ):
            return rule.category_id

    try:
        nature_int = int(nature)
    except (TypeError, ValueError):
        return None
    for rule in range_rules:
        if rule.nature_start <= nature_int <= rule.nature_end:
            return rule.category_id
    return None


def derive_mch2_rules(apps, schema_editor):
    AccountCodeMapping = apps.get_model("accounting", "AccountCodeMapping")
    SankeyAccountCodeRule = apps.get_model("finance", "SankeyAccountCodeRule")
    SankeyNatureRangeRule = apps.get_model("finance", "SankeyNatureRangeRule")

    code_rules = list(SankeyAccountCodeRule.objects.filter(scheme=MCH1))
    range_rules = sorted(
        SankeyNatureRangeRule.objects.filter(scheme=MCH1), key=lambda rule: (rule.priority, rule.nature_start)
    )

    # Track which MCH2 code each category claims, so two MCH1 sources that
    # disagree on the category for the same MCH2 code don't fight - the first
    # one seen wins and the rest are skipped for manual review in the admin.
    claimed: dict[tuple[str, str, str], int] = {}

    for mapping in AccountCodeMapping.objects.all():
        category_id = _resolve_mch1_category_id(
            mapping.mch1_function, mapping.mch1_nature, mapping.mch1_sub_account, code_rules, range_rules
        )
        if category_id is None:
            continue

        key = (mapping.mch2_function, mapping.mch2_nature, mapping.mch2_sub_account or "")
        existing_category_id = claimed.get(key)
        if existing_category_id is not None and existing_category_id != category_id:
            continue
        claimed[key] = category_id

        SankeyAccountCodeRule.objects.get_or_create(
            scheme=MCH2,
            function=key[0],
            nature=key[1],
            sub_account=key[2],
            defaults={"category_id": category_id},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0004_seed_sankey_rules"),
        ("accounting", "0016_accountcodemapping"),
    ]

    operations = [
        # Reversal is a no-op, not a bulk delete: scheme=mch2 rows also include
        # the hand-seeded ones from 0004 (Police, Péréquation, Sécurité
        # sociale), which this migration must not wipe out on rollback.
        migrations.RunPython(derive_mch2_rules, migrations.RunPython.noop),
    ]
