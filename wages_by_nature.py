import csv
import sys

from budgetis.accounting.models import Account


NATURES = ["301", "303", "304", "305"]
YEARS = [2025, 2024, 2023]

accounts = (
    Account.objects.filter(nature__in=NATURES, is_budget=False, year__in=YEARS)
    .order_by("nature", "function", "year")
    .values("nature", "function", "label", "year", "charges", "revenues")
)

# Pivot: key = (nature, function, label), value = {year: amount}
rows = {}
for a in accounts:
    key = (a["nature"], a["function"], a["label"])
    amount = a["charges"] if a["charges"] else a["revenues"]
    rows.setdefault(key, {})[a["year"]] = amount

writer = csv.writer(sys.stdout, delimiter="\t")
writer.writerow(["Nature", "Fonction", "Libellé", "Comptes 2025", "Comptes 2024", "Comptes 2023"])

for (nature, function, label), years_data in sorted(rows.items()):
    writer.writerow(
        [
            nature,
            function,
            label,
            years_data.get(2025, ""),
            years_data.get(2024, ""),
            years_data.get(2023, ""),
        ]
    )
