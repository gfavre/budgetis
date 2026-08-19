from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0012_alter_account_sub_account"),
    ]

    operations = [
        migrations.AlterField(
            model_name="accountgroup",
            name="code",
            field=models.CharField(db_index=True, max_length=5),
        ),
        migrations.AddField(
            model_name="accountgroup",
            name="scheme",
            field=models.CharField(
                choices=[("mch1", "MCH1"), ("mch2", "MCH2")],
                default="mch1",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="accountgroup",
            name="level",
            field=models.PositiveSmallIntegerField(default=3),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="accountgroup",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="accounting.accountgroup",
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="scheme",
            field=models.CharField(
                choices=[("mch1", "MCH1"), ("mch2", "MCH2")],
                default="mch1",
                max_length=10,
                verbose_name="Scheme",
            ),
        ),
    ]
