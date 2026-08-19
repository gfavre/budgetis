from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0014_accountgroup_merge_hierarchy_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="accountgroup",
            name="supergroup",
        ),
        migrations.DeleteModel(
            name="SuperGroup",
        ),
        migrations.DeleteModel(
            name="MetaGroup",
        ),
    ]
