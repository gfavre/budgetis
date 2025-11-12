from budgetis.accounting.models import Account


for account in Account.objects.select_related("group").all():
    if account.full_code == "570.352":
        continue
    try:
        group_label = account.group.label.upper().strip()
    except AttributeError:
        continue
    label = account.label.strip()
    # Si le label du compte commence par celui du groupe (insensible à la casse)
    if label.upper().startswith(group_label):
        # On supprime la partie du groupe et l'espace éventuel suivant
        new_label = label[len(group_label) :].lstrip(" -–_:")
        if not new_label:
            continue
        print(f"{account.full_code}: '{label}' → '{new_label}'")
        account.label = new_label
        account.save(update_fields=["label"])


for account in Account.objects.select_related("group").all():
    if account.label[0].islower():
        account.label = account.label[0].upper() + account.label[1:]
        account.save(update_fields=["label"])


for account in Account.objects.select_related("group").all():
    label = account.label.strip()
    group_label = "SERVICE EAUX"
    if label.startswith(group_label):
        new_label = label[len(group_label) :].lstrip(" -–_:")
        if not new_label:
            continue
        print(f"{account.full_code}: '{label}' → '{new_label}'")
        account.label = new_label
        account.save(update_fields=["label"])


for account in Account.objects.select_related("group").all():
    label = account.label.strip()
    group_label = "BATI. COMM"
    if label.startswith(group_label):
        new_label = label[len(group_label) :].lstrip(" -–_:")
        if not new_label:
            continue
        print(f"{account.full_code}: '{label}' → '{new_label}'")
        account.label = new_label
        account.save(update_fields=["label"])


def cleanup_group(group_label):
    for account in Account.objects.select_related("group").all():
        label = account.label.strip()
        if label.startswith(group_label):
            new_label = label[len(group_label) :].lstrip(" -–_:")
            if not new_label:
                continue
            print(f"{account.full_code}: '{label}' → '{new_label}'")
            account.label = new_label
            account.save(update_fields=["label"])


cleanup_group("AUBERGE et APPT")
cleanup_group("D'UNE FONTAINE")
cleanup_group("1912 - LE MONTANT")
cleanup_group("BÂTIMENT EGLISE")
cleanup_group("LE GOSSAN")
cleanup_group("CASERNE")
cleanup_group("Gare 5")
