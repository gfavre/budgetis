"""Describe the crosswalk without inferring amounts or allocation weights."""

from collections import defaultdict
from re import fullmatch

from budgetis.accounting.models import Account
from budgetis.accounting.models import AccountCodeMapping
from budgetis.common.models import ChartScheme


def is_operating_code(scheme, function, nature):
    """Operating natures are 3xx/4xx in MCH1 and 3xxx/4xxx in MCH2.

    Historical BDI balance codes use a 9xxx first segment; their second
    segment is a subdivision, not an operating nature.
    """
    if scheme == ChartScheme.MCH1:
        return bool(fullmatch(r"[34][0-9]{2}", nature)) and not fullmatch(r"9[0-9]{3}", function)
    return scheme == ChartScheme.MCH2 and bool(fullmatch(r"[34][0-9]{3}", nature))


def build_migration_report():
    forward = defaultdict(set)
    reverse = defaultdict(set)
    known = {ChartScheme.MCH1: {}, ChartScheme.MCH2: {}}
    # Latest imported label per code, independent of budget/actual duplicates.
    accounts = Account.objects.order_by("year", "is_budget", "pk").values_list(
        "scheme", "function", "nature", "sub_account", "label"
    )
    for scheme, function, nature, sub_account, label in accounts.iterator():
        if not is_operating_code(scheme, function, nature):
            continue
        code = f"{function}.{nature}" + (f".{sub_account}" if sub_account else "")
        known[scheme][code] = label
    for mapping in AccountCodeMapping.objects.all():
        source, target = mapping.mch1_code, mapping.mch2_code
        if mapping.mch1_function and is_operating_code(ChartScheme.MCH1, mapping.mch1_function, mapping.mch1_nature):
            forward[source]  # Keep sources even when their target is incomplete.
            if mapping.mch2_function and is_operating_code(
                ChartScheme.MCH2, mapping.mch2_function, mapping.mch2_nature
            ):
                forward[source].add(target)
                reverse[target].add(source)
    sources = set(forward) | set(known[ChartScheme.MCH1])
    targets = set(reverse) | set(known[ChartScheme.MCH2])
    mapped = {code for code in sources if forward[code]}
    split = {code for code in mapped if len(forward[code]) > 1}
    merged_targets = {code for code in targets if len(reverse[code]) > 1}
    merged = {code for code in mapped if forward[code] & merged_targets}
    complex_codes = split & merged
    simple = mapped - split - merged

    def rows(codes, links, scheme, other_scheme):
        return [
            {
                "code": code,
                "label": known[scheme].get(code, ""),
                "links": [
                    {"code": other, "label": known[other_scheme].get(other, "")} for other in sorted(links[code])
                ],
            }
            for code in sorted(codes)
        ]

    return {
        "reading_example_label": known[ChartScheme.MCH2].get("61500.3141.01", ""),
        "split_example": rows(
            ["100.303"] if len(forward["100.303"]) > 1 else sorted(split)[:1],
            forward,
            ChartScheme.MCH1,
            ChartScheme.MCH2,
        ),
        "merge_example": rows(
            ["96900.3420"] if len(reverse["96900.3420"]) > 1 else sorted(merged_targets)[:1],
            reverse,
            ChartScheme.MCH2,
            ChartScheme.MCH1,
        ),
        "total": len(sources),
        "unmapped": len(sources - mapped),
        "mapped": len(mapped),
        "split": len(split),
        "merged": len(merged),
        "merged_targets": len(merged_targets),
        "complex": len(complex_codes),
        "simple": len(simple),
        "recomposed": len(mapped - simple),
        "simple_percent": round(100 * len(simple) / len(mapped)) if mapped else 0,
        "recomposed_percent": round(100 * len(mapped - simple) / len(mapped)) if mapped else 0,
        "example": next(((code, next(iter(forward[code]))) for code in sorted(simple)), None),
        "forward_rows": rows(sources, forward, ChartScheme.MCH1, ChartScheme.MCH2),
        "reverse_rows": rows(targets, reverse, ChartScheme.MCH2, ChartScheme.MCH1),
    }
