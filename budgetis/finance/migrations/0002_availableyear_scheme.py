from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="availableyear",
            name="scheme",
            field=models.CharField(
                choices=[("mch1", "MCH1"), ("mch2", "MCH2")],
                default="mch1",
                max_length=10,
                verbose_name="Scheme",
            ),
        ),
    ]
