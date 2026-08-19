from django.db import migrations


def copy_metagroup_supergroup_into_accountgroup(apps, schema_editor):
    """
    Merge MetaGroup (level 1) and SuperGroup (level 2) into AccountGroup, wiring
    up the new self-referential `parent` chain. Existing AccountGroup rows (the
    former deepest/responsibility level) become level 3, parented to their
    migrated SuperGroup row. Nothing else needs touching: GroupResponsibility.group
    and Account.group keep pointing at the same AccountGroup primary keys.
    """
    MetaGroup = apps.get_model("accounting", "MetaGroup")
    SuperGroup = apps.get_model("accounting", "SuperGroup")
    AccountGroup = apps.get_model("accounting", "AccountGroup")

    metagroup_to_level1 = {}
    for mg in MetaGroup.objects.all():
        metagroup_to_level1[mg.id] = AccountGroup.objects.create(
            code=str(mg.code), label=mg.label, scheme="mch1", level=1, parent=None
        )

    supergroup_to_level2 = {}
    for sg in SuperGroup.objects.all():
        parent = metagroup_to_level1.get(sg.metagroup_id)
        supergroup_to_level2[sg.id] = AccountGroup.objects.create(
            code=str(sg.code), label=sg.label, scheme="mch1", level=2, parent=parent
        )

    for ag in AccountGroup.objects.filter(level=3):
        ag.parent = supergroup_to_level2.get(ag.supergroup_id)
        ag.save(update_fields=["parent"])


def reverse_copy(apps, schema_editor):
    AccountGroup = apps.get_model("accounting", "AccountGroup")
    AccountGroup.objects.filter(level=3).update(parent=None)
    AccountGroup.objects.filter(level__in=(1, 2)).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0013_accountgroup_add_hierarchy_fields"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="accountgroup",
            unique_together={("scheme", "level", "code")},
        ),
        migrations.AlterModelOptions(
            name="accountgroup",
            options={
                "ordering": ("scheme", "level", "code"),
                "verbose_name": "Account Group",
                "verbose_name_plural": "Account Groups",
            },
        ),
        migrations.RunPython(copy_metagroup_supergroup_into_accountgroup, reverse_copy),
    ]
