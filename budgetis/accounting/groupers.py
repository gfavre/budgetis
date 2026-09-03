from collections import OrderedDict
from decimal import Decimal

from budgetis.accounting.models import AccountGroup
from budgetis.accounting.models import GroupResponsibility
from budgetis.accounting.models import NatureGroup
from budgetis.accounting.nature import NATURE_GROUPS
from budgetis.accounting.views.data import AccountRow
from budgetis.common.models import ChartScheme


_COLS = ("col1_charges", "col1_revenues", "col2_charges", "col2_revenues", "col3_charges", "col3_revenues")


def _empty_totals() -> dict:
    return {col: Decimal(0) for col in _COLS}


def _load_group_ancestry(leaf_ids: set[int]) -> dict[int, AccountGroup]:
    """Load every AccountGroup reachable by walking `.parent` up from the given leaves."""
    groups_by_id: dict[int, AccountGroup] = {}
    frontier = set(leaf_ids)
    while frontier:
        fetched = list(AccountGroup.objects.filter(id__in=frontier))
        frontier = set()
        for group in fetched:
            groups_by_id[group.id] = group
            if group.parent_id and group.parent_id not in groups_by_id:
                frontier.add(group.parent_id)
    return groups_by_id


def _node_for(group: AccountGroup, responsibilities: dict) -> dict:
    return {
        "code": group.code,
        "label": group.label,
        "level": group.level,
        "children": {},
        "accounts": [],
        "responsible": responsibilities.get(group.id),
        **_empty_totals(),
    }


def _ensure_node(group: AccountGroup, *, nodes: dict, groups_by_id: dict, responsibilities: dict, roots: dict) -> dict:
    """Get-or-create the tree node for `group`, wiring it into its parent's children (or `roots`)."""
    if group.id in nodes:
        return nodes[group.id]

    node = _node_for(group, responsibilities)
    nodes[group.id] = node
    if group.parent_id:
        parent_node = _ensure_node(
            groups_by_id[group.parent_id],
            nodes=nodes,
            groups_by_id=groups_by_id,
            responsibilities=responsibilities,
            roots=roots,
        )
        parent_node["children"][group.code] = node
    else:
        roots[group.code] = node
    return node


def _accumulate(row: AccountRow, group: AccountGroup, *, nodes: dict, groups_by_id: dict) -> None:
    """Add `row`'s totals to `group`'s node and every one of its ancestors."""
    current = group
    while True:
        node = nodes[current.id]
        for col in _COLS:
            node[col] += getattr(row, col)
        if not current.parent_id:
            return
        current = groups_by_id[current.parent_id]


def _resolve_display_responsible(node: dict):
    """
    Leaves keep their own GroupResponsibility (set in _node_for). An ancestor
    (SuperGroup/MetaGroup) never has one of its own — it's purely a graphical
    grouping for the report — so it shows the single responsible shared by
    every descendant leaf function, or None when they disagree.
    """
    if not node["children"]:
        return node["responsible"]
    values = {_resolve_display_responsible(child) for child in node["children"].values()}
    node["responsible"] = values.pop() if len(values) == 1 else None
    return node["responsible"]


def build_grouped(rows: list[AccountRow], year: int) -> OrderedDict:
    """
    Build a tree of AccountGroup nodes (root -> ... -> leaf -> AccountRows),
    depth-agnostic: MCH1 groups nest 3 levels deep, MCH2 groups nest 4 levels
    deep, and this walks whatever `.parent` chain each account's group actually
    has, without knowing the depth up front.
    """
    if not rows:
        return OrderedDict()

    leaf_ids = {row.account.group_id for row in rows if row.account.group_id}
    if not leaf_ids:
        return OrderedDict()

    groups_by_id = _load_group_ancestry(leaf_ids)
    responsibilities = {
        r.group_id: r.responsible for r in GroupResponsibility.objects.filter(year=year).select_related("responsible")
    }

    nodes: dict[int, dict] = {}
    roots: dict[str, dict] = {}

    for row in rows:
        group = groups_by_id.get(row.account.group_id)
        if not group:
            continue

        leaf_node = _ensure_node(
            group, nodes=nodes, groups_by_id=groups_by_id, responsibilities=responsibilities, roots=roots
        )
        leaf_node["accounts"].append(row)
        _accumulate(row, group, nodes=nodes, groups_by_id=groups_by_id)

    for root in roots.values():
        _resolve_display_responsible(root)

    return _sort_tree(roots)


def _sort_tree(roots: dict) -> OrderedDict:
    result = OrderedDict()
    for code in sorted(roots):
        node = roots[code]
        _sort_node(node)
        result[code] = node
    return result


def _sort_node(node: dict) -> None:
    if node["children"]:
        node["children"] = OrderedDict(sorted(node["children"].items()))
        for child in node["children"].values():
            _sort_node(child)
    else:
        node["accounts"] = sorted(
            node["accounts"],
            key=lambda r: (r.account.function, r.account.nature, r.account.sub_account or ""),
        )


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


def _nature_group(nature: int, valid_codes: dict | None = None) -> int | None:
    try:
        n = int(str(nature)[:2])
    except (TypeError, ValueError):
        return None
    codes = NATURE_GROUPS if valid_codes is None else valid_codes
    return n if n in codes else None


def _nature_group_labels(scheme: str) -> tuple[dict, bool]:
    """
    MCH2 nature-group codes/labels come from the canton's official reference
    file (see import_mch2_nature_classification), which is authoritative and
    doesn't always match NATURE_GROUPS - a hand-written approximation kept
    only as the MCH1 fallback, since no equivalent reference file exists for it.

    Returns (labels, prune_empty_groups). NATURE_GROUPS lists every code ever
    used across MCH1's history, so an unused one is pruned; the official MCH2
    set is small and complete enough that an all-zero group (not yet budgeted)
    is worth surfacing rather than hiding.
    """
    if scheme == ChartScheme.MCH2:
        mch2_groups = NatureGroup.objects.filter(scheme=ChartScheme.MCH2, level=2)
        if mch2_groups.exists():
            return OrderedDict((int(g.code), g.label) for g in mch2_groups.order_by("code")), False
    return NATURE_GROUPS, True


def build_nature_grouped(rows: list[AccountRow]) -> OrderedDict:
    """Group AccountRows by nature code (30–49)."""
    scheme = rows[0].account.scheme if rows else ChartScheme.MCH1
    labels, prune_empty = _nature_group_labels(scheme)
    grouped = OrderedDict(
        (gid, {"code": str(gid), "label": str(label), **_empty_totals()}) for gid, label in labels.items()
    )

    for row in rows:
        gid = _nature_group(int(row.account.nature), labels)
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

    if prune_empty:
        for gid in list(grouped):
            if not any(grouped[gid][col] for col in _COLS):
                grouped.pop(gid)

    return grouped


def _nature_tree_skeleton(groups: list[NatureGroup]) -> tuple[dict, dict, dict]:
    """Build empty nodes for every group, wired to their parent's children, indexed by (level, code)."""
    code_by_id = {g.id: g.code for g in groups}
    nodes = {
        g.code: {"code": g.code, "label": g.label, "level": g.level, "children": OrderedDict(), **_empty_totals()}
        for g in groups
    }
    roots: dict[str, dict] = {}
    by_level: dict[int, dict] = {1: {}, 2: {}, 3: {}}
    for g in sorted(groups, key=lambda g: g.level):
        by_level[g.level][g.code] = nodes[g.code]
        if g.parent_id:
            nodes[code_by_id[g.parent_id]]["children"][g.code] = nodes[g.code]
        else:
            roots[g.code] = nodes[g.code]
    return nodes, roots, by_level


def build_nature_tree(rows: list[AccountRow]) -> OrderedDict | None:
    """
    Build a 3-level nature tree (1 Charges/Revenus -> 2 family -> 3 sub-family)
    from the official MCH2 nature classification. Stops at level 3 by design -
    level 4 (individual nature codes) is one step too deep for this report.

    Returns None when the scheme has no NatureGroup data (MCH1's NATURE_GROUPS
    fallback has no level 1/3 to build a tree from - build_nature_grouped's flat
    table stays the report for it).
    """
    if not rows:
        return None
    scheme = rows[0].account.scheme
    groups = list(NatureGroup.objects.filter(scheme=scheme, level__in=(1, 2, 3)))
    if not groups:
        return None

    nodes, roots, by_level = _nature_tree_skeleton(groups)

    for row in rows:
        nature = str(row.account.nature)
        for level in (1, 2, 3):
            node = by_level[level].get(nature[:level])
            if node is None:
                continue
            for col in _COLS:
                node[col] += getattr(row, col)

    for node in nodes.values():
        node["children"] = OrderedDict(sorted(node["children"].items()))

    return OrderedDict(sorted(roots.items()))
