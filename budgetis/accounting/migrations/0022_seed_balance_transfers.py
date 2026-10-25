from django.db import migrations


# Florence's mapping clarification, supplied with the 14 October 2026 crosswalk.
# Target balance account numbers have not yet been provided.
BALANCE_TRANSFERS = ("452.318.1", "452.436.1", "650.317", "650.452")


def seed_balance_transfers(apps, schema_editor):
    transfer = apps.get_model("accounting", "AccountBalanceTransfer")
    for code in BALANCE_TRANSFERS:
        transfer.objects.using(schema_editor.connection.alias).get_or_create(mch1_code=code)


class Migration(migrations.Migration):
    dependencies = [("accounting", "0021_account_balance_transfer")]
    operations = [migrations.RunPython(seed_balance_transfers, migrations.RunPython.noop)]
