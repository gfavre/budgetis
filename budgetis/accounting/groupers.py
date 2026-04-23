from collections import OrderedDict
from decimal import Decimal

from budgetis.accounting.models import GroupResponsibility
from budgetis.accounting.nature import NATURE_GROUPS
from budgetis.accounting.views.data import AccountRow


_COLS = ("col1_charges", "col1_revenues", "col2_charges", "col2_revenues", "col3_charges", "col3_revenues")


def _empty_totals() -> dict:
    return {col: Decimal(0) for col in _COLS}


def build_grouped(rows: list[AccountRow], year: int) -> OrderedDict:
    """Build MetaGroup → SuperGroup → AccountGroup → AccountRow nested structure."""
    if not rows:
        return OrderedDict()

    responsibilities = {
        r.group_id: r.responsible for r in GroupResponsibility.objects.filter(year=year).select_related("responsible")
    }

    raw: dict = {}
    for row in rows:
        acc = row.account
        group = acc.group
        supergroup = group.supergroup if group else None
        metagroup = supergroup.metagroup if supergroup else None
        if not (group and supergroup and metagroup):
            continue

        mg = raw.setdefault(metagroup.code, {"label": metagroup.label, "supergroups": {}, **_empty_totals()})
        sg = mg["supergroups"].setdefault(
            supergroup.code, {"label": supergroup.label, "groups": {}, **_empty_totals()}
        )
        ag = sg["groups"].setdefault(
            group.code,
            {
                "label": group.label,
                "accounts": [],
                "responsible": responsibilities.get(group.id),
                **_empty_totals(),
            },
        )

        ag["accounts"].append(row)
        for col in _COLS:
            val = getattr(row, col)
            ag[col] += val
            sg[col] += val
            mg[col] += val

    return _sort_grouped(raw)


def _sort_grouped(raw: dict) -> OrderedDict:
    result = OrderedDict()
    for mg_code in sorted(raw):
        mg = raw[mg_code]
        sorted_sg = OrderedDict()
        for sg_code in sorted(mg["supergroups"]):
            sg = mg["supergroups"][sg_code]
            sorted_ag = OrderedDict()
            for ag_code in sorted(sg["groups"]):
                ag = sg["groups"][ag_code]
                ag["accounts"] = sorted(
                    ag["accounts"],
                    key=lambda r: (r.account.function, r.account.nature, r.account.sub_account or ""),
                )
                sorted_ag[ag_code] = ag
            sg["groups"] = sorted_ag
            sorted_sg[sg_code] = sg
        mg["supergroups"] = sorted_sg
        result[mg_code] = mg
    return result


def build_summary(grouped: OrderedDict) -> dict:
    """Build global summary from any grouped structure using col1/col2/col3 keys."""
    rows = []
    totals = _empty_totals()

    for code, entry in grouped.items():
        row = {"code": code, "label": entry["label"]}
        for col in _COLS:
            row[col] = entry[col]
            totals[col] += entry[col]
        rows.append(row)

    for i in (1, 2, 3):
        diff = totals[f"col{i}_revenues"] - totals[f"col{i}_charges"]
        totals[f"col{i}_diff"] = diff
        totals[f"balanced_col{i}"] = max(totals[f"col{i}_charges"], totals[f"col{i}_revenues"])

    return {"rows": rows, "totals": totals}


def _nature_group(nature: int) -> int | None:
    try:
        n = int(str(nature)[:2])
    except (TypeError, ValueError):
        return None
    return n if n in NATURE_GROUPS else None


def build_nature_grouped(rows: list[AccountRow]) -> OrderedDict:
    """Group AccountRows by nature code (30–49)."""
    grouped = OrderedDict(
        (gid, {"code": gid, "label": str(label), **_empty_totals()}) for gid, label in NATURE_GROUPS.items()
    )

    for row in rows:
        gid = _nature_group(int(row.account.nature))
        if gid is None:
            continue
        entry = grouped[gid]
        if 30 <= gid <= 39:  # noqa: PLR2004
            entry["col1_charges"] += row.col1_charges
            entry["col2_charges"] += row.col2_charges
            entry["col3_charges"] += row.col3_charges
        elif 40 <= gid <= 49:  # noqa: PLR2004
            entry["col1_revenues"] += row.col1_revenues
            entry["col2_revenues"] += row.col2_revenues
            entry["col3_revenues"] += row.col3_revenues

    # remove empty rows
    for gid in list(grouped):
        if not any(grouped[gid][col] for col in _COLS):
            grouped.pop(gid)

    return grouped
